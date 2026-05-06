#!/usr/bin/env python3
"""
PLAN Registry — Hermes 管理所有 PLAN Agent 的中央系統
=======================================================
"""

import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from collections import deque

# fcntl is POSIX-only; provide a no-op fallback so the module imports on Windows
try:
    import fcntl  # type: ignore
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - Windows fallback
    _HAS_FCNTL = False

    class _FcntlShim:
        LOCK_EX = 0
        LOCK_SH = 0
        LOCK_UN = 0

        @staticmethod
        def flock(_fd, _op):
            return None

    fcntl = _FcntlShim()  # type: ignore

HERMES_HOME = Path.home() / ".hermes"
REGISTRY_DIR = HERMES_HOME / "plan_registry"
REGISTRY_FILE = REGISTRY_DIR / "registry.json"
REGISTRY_LOG = REGISTRY_DIR / "registry_log.json"
EVENTS_LOG = REGISTRY_DIR / "events.jsonl"

from shared_deps import DEPENDENCY_GRAPH, COMPONENT_GRAPH, COMPONENT_TO_PLAN, lift_to_plan

REGISTRY_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path, default=None):
    try:
        p = os.path.expanduser(str(path))
        with open(p, 'r', encoding='utf-8-sig') as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            except OSError:
                pass
            try:
                text = f.read()
            finally:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        return json.loads(text.replace('\r\n', '\n'))
    except Exception:
        return default if default is not None else {}


def _save_json_unlocked(path, data):
    """Atomic JSON save WITHOUT acquiring the registry lock.

    Use this only from inside a `with _registry_lock(...)` block, otherwise
    use _save_json (which acquires the lock for you).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + f'.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _save_json(path, data):
    """
    Atomic, multi-writer-safe JSON save.
      1. Each writer uses a UNIQUE tmp file (PID + uuid) so writers never
         truncate each other's tmp content.
      2. The destination file is opened separately and held under LOCK_EX
         while the tmp is rendered, so concurrent _save_json calls serialize.
      3. os.replace() atomically swaps tmp -> dest at the end.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + f'.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}'

    lock_path = str(path) + '.lock'
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        except OSError:
            pass
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, str(path))
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        try:
            os.close(lock_fd)
        except OSError:
            pass
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


@contextmanager
def _registry_lock(path):
    """Hold an exclusive advisory lock for read-modify-write transactions."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lock_path = str(path) + '.lock'
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        except OSError:
            pass
        yield
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(lock_fd)
        except OSError:
            pass


def _log(action, detail):
    logs = _load_json(REGISTRY_LOG, [])
    if not isinstance(logs, list):
        logs = []
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "detail": detail
    })
    if len(logs) > 500:
        logs = logs[-500:]
    _save_json(REGISTRY_LOG, logs)


def log_event(event_type, plan_id, detail):
    """將事件追加到 events.jsonl（一行一事件）"""
    event = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        "plan_id": plan_id,
        "detail": detail,
    }
    line = json.dumps(event, ensure_ascii=False, default=str)
    with open(EVENTS_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


class PlanRegistry:
    def __init__(self):
        with _registry_lock(REGISTRY_FILE):
            self.registry = _load_json(REGISTRY_FILE, {"plans": {}, "created_at": datetime.now().isoformat()})
        if "plans" not in self.registry:
            self.registry["plans"] = {}

    def _reload(self):
        self.registry = _load_json(REGISTRY_FILE, {"plans": {}, "created_at": datetime.now().isoformat()})
        if "plans" not in self.registry:
            self.registry["plans"] = {}

    def save(self):
        self.registry["last_updated"] = datetime.now().isoformat()
        with _registry_lock(REGISTRY_FILE):
            disk = _load_json(REGISTRY_FILE, {"plans": {}})
            if "plans" in disk:
                for pid, val in disk["plans"].items():
                    if pid not in self.registry["plans"]:
                        self.registry["plans"][pid] = val
            _save_json_unlocked(REGISTRY_FILE, self.registry)

    def _save_locked(self):
        """Save assuming caller already holds _registry_lock(REGISTRY_FILE).

        Uses _save_json_unlocked so we don't deadlock by trying to re-acquire
        the same advisory flock from this process.
        """
        self.registry["last_updated"] = datetime.now().isoformat()
        _save_json_unlocked(REGISTRY_FILE, self.registry)

    def register(self, plan_id, name, description, heartbeat_path,
                 report_path=None, command_path=None, response_path=None,
                 domain=None, owner="hermes", metadata=None):
        now = datetime.now().isoformat()
        plan_entry = {
            "plan_id": plan_id, "name": name, "description": description,
            "domain": domain or "general", "owner": owner, "created_at": now,
            "status": "registered",
            "heartbeat": {"path": str(heartbeat_path), "last_read": None,
                          "last_score": None, "last_status": None},
            "paths": {
                "report": str(report_path) if report_path else None,
                "command": str(command_path) if command_path else None,
                "response": str(response_path) if response_path else None,
            },
            "metadata": metadata or {},
            "stats": {"total_heartbeats": 0, "total_commands": 0,
                      "last_heartbeat": None, "last_command": None},
        }
        with _registry_lock(REGISTRY_FILE):
            self._reload()
            self.registry["plans"][plan_id] = plan_entry
            self._save_locked()
        _log("register", f"註冊 PLAN: {plan_id} ({name})")
        log_event("plan_registered", plan_id, f"Registered: {name}")
        return plan_entry

    def unregister(self, plan_id):
        with _registry_lock(REGISTRY_FILE):
            self._reload()
            if plan_id in self.registry["plans"]:
                del self.registry["plans"][plan_id]
                self._save_locked()
                _log("unregister", f"移除 PLAN: {plan_id}")
                return True
        return False

    def list_plans(self):
        plans = self.registry.get("plans", {})
        return [{
            "plan_id": pid, "name": p["name"], "domain": p["domain"],
            "status": p["status"], "description": p["description"][:80],
        } for pid, p in plans.items()]

    def get_plan(self, plan_id):
        return self.registry.get("plans", {}).get(plan_id)

    def get_plans_by_domain(self, domain):
        return {pid: p for pid, p in self.registry.get("plans", {}).items()
                if p.get("domain") == domain}

    def read_heartbeat(self, plan_id):
        plan = self.get_plan(plan_id)
        if not plan:
            return {"error": f"PLAN '{plan_id}' 未註冊"}
        hb_path = plan.get("heartbeat", {}).get("path")
        if not hb_path:
            return {"error": f"PLAN '{plan_id}' 沒有設定心跳路徑"}
        heartbeat = _load_json(hb_path)
        if not heartbeat:
            return {"error": f"心跳檔案不存在或無法讀取: {hb_path}"}

        plan["heartbeat"]["last_read"] = datetime.now().isoformat()
        plan["heartbeat"]["last_score"] = heartbeat.get("health_score")
        plan["heartbeat"]["last_status"] = heartbeat.get("status")
        plan["stats"]["total_heartbeats"] = plan["stats"].get("total_heartbeats", 0) + 1
        plan["stats"]["last_heartbeat"] = datetime.now().isoformat()

        if heartbeat.get("status") == "CRITICAL":
            plan["status"] = "critical"
        elif heartbeat.get("status") == "HEALTHY":
            plan["status"] = "active"

        with _registry_lock(REGISTRY_FILE):
            self._reload()
            if plan_id in self.registry["plans"]:
                self.registry["plans"][plan_id].update({
                    "heartbeat": plan["heartbeat"],
                    "stats": plan["stats"],
                    "status": plan["status"],
                })
                self._save_locked()

        log_event("heartbeat_read", plan_id, f"Score: {heartbeat.get('health_score')}, Status: {heartbeat.get('status')}")
        return heartbeat

    def read_all_heartbeats(self):
        results = {}
        for plan_id in self.registry.get("plans", {}):
            results[plan_id] = self.read_heartbeat(plan_id)
        return results

    def send_command(self, plan_id, command_type, params=None):
        plan = self.get_plan(plan_id)
        if not plan:
            return {"error": f"PLAN '{plan_id}' 未註冊"}
        cmd_path = plan.get("paths", {}).get("command")
        if not cmd_path:
            return {"error": f"PLAN '{plan_id}' 沒有設定指令路徑"}
        command = {
            "command_id": f"CMD_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "type": command_type, "params": params or {},
            "issued_by": "hermes", "issued_at": datetime.now().isoformat(),
            "status": "pending",
        }
        _save_json(cmd_path, command)

        plan["stats"]["total_commands"] = plan["stats"].get("total_commands", 0) + 1
        plan["stats"]["last_command"] = datetime.now().isoformat()
        with _registry_lock(REGISTRY_FILE):
            self._reload()
            if plan_id in self.registry["plans"]:
                self.registry["plans"][plan_id]["stats"] = plan["stats"]
                self._save_locked()

        _log("command", f"指令 {command_type} → {plan_id}")
        log_event("command_sent", plan_id, f"Command: {command_type}")
        return command

    def read_response(self, plan_id):
        plan = self.get_plan(plan_id)
        if not plan:
            return {"error": f"PLAN '{plan_id}' 未註冊"}
        resp_path = plan.get("paths", {}).get("response")
        if not resp_path:
            return {"error": f"PLAN '{plan_id}' 沒有設定回應路徑"}
        return _load_json(resp_path, {"error": "無回應檔案"})

    def check_stale_heartbeats(self, timeout_minutes=30):
        stale = []
        now = datetime.now()
        for pid, plan in self.registry.get("plans", {}).items():
            last_hb = plan.get("stats", {}).get("last_heartbeat")
            if last_hb is None:
                stale.append({"plan_id": pid, "last_heartbeat": None,
                              "minutes_since": None,
                              "reason": "No heartbeat recorded"})
                log_event("stale_detected", pid, "No heartbeat recorded")
                continue
            try:
                last_dt = datetime.fromisoformat(last_hb)
                diff = now - last_dt
                if diff.total_seconds() > timeout_minutes * 60:
                    stale.append({"plan_id": pid, "last_heartbeat": last_hb,
                                  "minutes_since": round(diff.total_seconds() / 60, 1),
                                  "reason": f"Last heartbeat {round(diff.total_seconds()/60,1)} min ago"})
                    plan["status"] = "stale"
                    log_event("stale_detected", pid,
                              f"Last heartbeat {round(diff.total_seconds()/60,1)} min ago (threshold: {timeout_minutes})")
            except (ValueError, TypeError):
                stale.append({"plan_id": pid, "last_heartbeat": last_hb,
                              "minutes_since": None,
                              "reason": f"Invalid timestamp: {last_hb}"})
                log_event("stale_detected", pid, f"Invalid timestamp: {last_hb}")
        if stale:
            stale_ids = {item["plan_id"] for item in stale if item.get("reason", "").startswith("Last heartbeat")}
            if stale_ids:
                with _registry_lock(REGISTRY_FILE):
                    self._reload()
                    for sid in stale_ids:
                        if sid in self.registry["plans"]:
                            self.registry["plans"][sid]["status"] = "stale"
                    self._save_locked()
        return stale

    def get_affected_plans(self, plan_id):
        """Walks DEPENDENCY_GRAPH (PLAN level) AND COMPONENT_GRAPH (lifted)."""
        start_plan = lift_to_plan(plan_id)
        visited = set()
        affected_plans = []

        queue = deque([start_plan])
        while queue:
            current = queue.popleft()
            for dep in DEPENDENCY_GRAPH.get(current, []):
                if dep not in visited:
                    visited.add(dep)
                    affected_plans.append(dep)
                    queue.append(dep)

        comp_visited = set()
        comp_queue = deque([plan_id])
        while comp_queue:
            current = comp_queue.popleft()
            for dep in COMPONENT_GRAPH.get(current, []):
                if dep not in comp_visited:
                    comp_visited.add(dep)
                    comp_queue.append(dep)
                    plan = lift_to_plan(dep)
                    if plan and plan != start_plan and plan not in visited:
                        visited.add(plan)
                        affected_plans.append(plan)

        return affected_plans

    def correlate_incidents(self):
        problem_plans = set()
        for pid, plan in self.registry.get("plans", {}).items():
            status = plan.get("status", "")
            if status in ("stale", "critical", "dead"):
                problem_plans.add(pid)
            hb_status = plan.get("heartbeat", {}).get("last_status")
            if hb_status == "CRITICAL":
                problem_plans.add(pid)

        reverse_graph = {}
        for parent, children in DEPENDENCY_GRAPH.items():
            for child in children:
                reverse_graph.setdefault(child, []).append(parent)
        for parent, children in COMPONENT_GRAPH.items():
            p_plan = lift_to_plan(parent)
            for child in children:
                c_plan = lift_to_plan(child)
                if c_plan and p_plan and c_plan != p_plan:
                    reverse_graph.setdefault(c_plan, []).append(p_plan)

        visited = set()
        incidents = []
        for plan_id in problem_plans:
            if plan_id in visited:
                continue
            group = set()
            queue = deque([plan_id])
            while queue:
                current = queue.popleft()
                if current in visited:
                    continue
                visited.add(current)
                group.add(current)
                for parent in reverse_graph.get(current, []):
                    if parent in problem_plans and parent not in visited:
                        queue.append(parent)
                children_plan = list(DEPENDENCY_GRAPH.get(current, []))
                for child in COMPONENT_GRAPH.get(current, []):
                    lifted = lift_to_plan(child)
                    if lifted and lifted != current:
                        children_plan.append(lifted)
                for child in children_plan:
                    if child in problem_plans and child not in visited:
                        queue.append(child)

            if len(group) >= 2:
                incidents.append({
                    "group_id": f"INC_{len(incidents)+1}",
                    "plans": sorted(group),
                    "likely_root_cause": sorted(group)[0],
                    "count": len(group),
                })
            else:
                incidents.append({
                    "group_id": f"INC_{len(incidents)+1}",
                    "plans": sorted(group),
                    "likely_root_cause": sorted(group)[0],
                    "count": 1,
                    "isolated": True,
                })
        return incidents

    def health_overview(self):
        plans = self.registry.get("plans", {})
        overview = {
            "timestamp": datetime.now().isoformat(),
            "total_plans": len(plans),
            "by_status": {},
            "by_domain": {},
            "plans": [],
        }

        for pid, plan in plans.items():
            status = plan.get("status", "unknown")
            domain = plan.get("domain", "unknown")
            hb = self.read_heartbeat(pid)

            if isinstance(hb, dict) and hb.get("exclude_from_overview"):
                continue
            if isinstance(hb, dict) and hb.get("status") in ("NOT_CONFIGURED", "DISABLED", "UNREGISTERED"):
                continue

            overview["by_status"][status] = overview["by_status"].get(status, 0) + 1
            overview["by_domain"][domain] = overview["by_domain"].get(domain, 0) + 1

            overview["plans"].append({
                "plan_id": pid,
                "name": plan["name"],
                "domain": domain,
                "status": status,
                "health_score": hb.get("health_score") if isinstance(hb, dict) and "error" not in hb else "N/A",
                "last_heartbeat": plan.get("stats", {}).get("last_heartbeat"),
                "description": plan.get("description", plan.get("name", "N/A"))[:60],
            })

        if overview["by_status"].get("critical", 0) > 0:
            overview["global_status"] = "CRITICAL"
            overview["global_emoji"] = "🔴"
        elif overview["by_status"].get("active", 0) == len(overview["plans"]) and len(overview["plans"]) > 0:
            overview["global_status"] = "ALL_HEALTHY"
            overview["global_emoji"] = "🟢"
        else:
            overview["global_status"] = "ATTENTION"
            overview["global_emoji"] = "🟡"

        stale = self.check_stale_heartbeats()
        overview["stale_heartbeats"] = stale
        if stale:
            overview["global_status"] = "STALE_WARNING"
            overview["global_emoji"] = "🟠"
            for item in stale:
                log_event("health_overview_stale", item["plan_id"], item["reason"])

        incidents = self.correlate_incidents()
        overview["incidents"] = incidents
        correlated = [inc for inc in incidents if not inc.get("isolated")]
        if correlated:
            overview["correlated_incidents"] = len(correlated)
            for inc in correlated:
                log_event("health_overview_correlated", ",".join(inc["plans"]),
                          f"Group {inc['group_id']}: {inc['count']} related plans")

        return overview


def cli_list():
    reg = PlanRegistry()
    plans = reg.list_plans()
    if not plans:
        print("  目前沒有已註冊的 PLAN Agent")
        return
    print(f"\n  已註冊的 PLAN Agent ({len(plans)} 個):")
    print(f"  {'─'*60}")
    for p in plans:
        emoji = {"active": "🟢", "critical": "🔴", "paused": "⏸️",
                 "registered": "📋", "dead": "💀"}.get(p["status"], "❓")
        print(f"  {emoji} {p['plan_id']:20s} | {p['domain']:10s} | {p['description']}")
    print()


def cli_status(plan_id=None, show_all=False):
    reg = PlanRegistry()
    if show_all:
        overview = reg.health_overview()
        print(f"\n  {overview['global_emoji']} 全域狀態: {overview['global_status']}")
        print(f"  PLAN 總數: {overview['total_plans']}")
        print(f"  按狀態: {overview['by_status']}")
        print(f"  按領域: {overview['by_domain']}")
        print()
        for p in overview["plans"]:
            score = p["health_score"]
            score_str = f"{score}/100" if isinstance(score, (int, float)) else str(score)
            print(f"    {p['plan_id']:20s} | {score_str:10s} | {p['name']}")
        print()
        return

    if not plan_id:
        print("  用法: plan_registry.py status <plan_id> 或 status --all")
        return

    plan = reg.get_plan(plan_id)
    if not plan:
        print(f"  PLAN '{plan_id}' 未註冊")
        return

    hb = reg.read_heartbeat(plan_id)
    print(f"\n  PLAN: {plan['name']} ({plan['plan_id']})")
    print(f"  {'─'*50}")
    print(f"  領域: {plan['domain']}")
    print(f"  描述: {plan['description']}")
    print(f"  狀態: {plan['status']}")
    print(f"  創建: {plan['created_at']}")

    if isinstance(hb, dict) and "error" not in hb:
        print(f"\n  最新心跳:")
        print(f"    健康分數: {hb.get('health_score', 'N/A')}/100")
        print(f"    狀態: {hb.get('status', 'N/A')}")
        print(f"    問題數: {hb.get('total_issues', 'N/A')}")
        if hb.get("critical_issues"):
            print(f"    🔴 CRITICAL: {', '.join(hb['critical_issues'][:3])}")
    else:
        print(f"\n  心跳: {hb.get('error', '無法讀取')}")

    print(f"\n  統計:")
    print(f"    心跳次數: {plan['stats'].get('total_heartbeats', 0)}")
    print(f"    指令次數: {plan['stats'].get('total_commands', 0)}")
    print()


def cli_health():
    cli_status(show_all=True)


def cli_stale():
    reg = PlanRegistry()
    stale = reg.check_stale_heartbeats()
    if not stale:
        print("  ✅ 所有 PLAN 心跳正常")
        return
    print(f"\n  🟠 心跳超時的 PLAN ({len(stale)} 個):")
    print(f"  {'─'*60}")
    for item in stale:
        pid = item["plan_id"]
        mins = item.get("minutes_since")
        reason = item["reason"]
        if mins is not None:
            print(f"  ⏰ {pid:20s} | {mins:6.1f} min ago | {reason}")
        else:
            print(f"  ⏰ {pid:20s} | {'N/A':>6s}       | {reason}")
    print()


def cli_incidents():
    reg = PlanRegistry()
    incidents = reg.correlate_incidents()
    if not incidents:
        print("  ✅ 無問題 PLAN，無事件可關聯")
        return
    print(f"\n  🔍 事件關聯分析 ({len(incidents)} 組):")
    print(f"  {'─'*60}")
    for inc in incidents:
        gid = inc["group_id"]
        plans_str = ", ".join(inc["plans"])
        count = inc["count"]
        if inc.get("isolated"):
            print(f"  {gid} [獨立] {plans_str}")
        else:
            print(f"  {gid} [關聯 x{count}] 根因: {inc['likely_root_cause']}")
            print(f"         受影響: {plans_str}")
    print()


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] == "list":
        cli_list()
    elif args[0] == "status":
        if len(args) > 1 and args[1] == "--all":
            cli_status(show_all=True)
        elif len(args) > 1:
            cli_status(plan_id=args[1])
        else:
            cli_status()
    elif args[0] == "health":
        cli_health()
    elif args[0] == "stale":
        cli_stale()
    elif args[0] == "incidents":
        cli_incidents()
    elif args[0] == "register":
        if "--json" in args:
            idx = args.index("--json")
            if idx + 1 < len(args):
                data = json.loads(args[idx + 1])
                reg = PlanRegistry()
                result = reg.register(**data)
                print(f"  已註冊: {result['plan_id']}")
        else:
            print("  用法: plan_registry.py register --json '{...}'")
    elif args[0] == "command":
        if len(args) >= 3:
            reg = PlanRegistry()
            result = reg.send_command(args[1], args[2],
                                      params=json.loads(args[3]) if len(args) > 3 else None)
            print(f"  指令已發送: {json.dumps(result, indent=2, ensure_ascii=False)}")
        else:
            print("  用法: plan_registry.py command <plan_id> <command_type> [params_json]")
    else:
        print("  用法: plan_registry.py [list|status|health|stale|incidents|register|command]")
