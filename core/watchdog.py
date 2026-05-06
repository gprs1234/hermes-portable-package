#!/usr/bin/env python3
"""
PLAN Registry Watchdog — Independent health monitor for all PLAN Agents.

Usage:
    python3 watchdog.py              # One-shot check all plans
    python3 watchdog.py --fix        # Check + auto-restart stale/dead plans
    python3 watchdog.py --monitor    # Continuous mode (check every 5 min)
    python3 watchdog.py --json       # Output as JSON instead of human-readable
"""

import json
import os
import sys
import time
import subprocess
import signal
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────
REGISTRY_PATH = Path.home() / ".hermes" / "plan_registry" / "registry.json"
STATE_PATH = Path.home() / ".hermes" / "plan_registry" / "watchdog_state.json"
HEARTBEAT_PATH = Path.home() / ".hermes" / "plan_registry" / "watchdog_heartbeat.json"
ALERT_LOG = Path.home() / ".hermes" / "plan_registry" / "watchdog_alerts.jsonl"

STALE_THRESHOLD = timedelta(minutes=30)
DEAD_THRESHOLD = timedelta(hours=2)
WATCHDOG_DEAD_THRESHOLD = timedelta(minutes=10)
MONITOR_INTERVAL = 300

MAX_RESTARTS = 3
RESTART_WINDOW = 1800

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def now_utc():
    return datetime.now(timezone.utc)


def parse_timestamp(ts_str):
    if not ts_str:
        return None
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except (ValueError, TypeError):
        return None


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)
    os.replace(tmp, str(path))


def append_jsonl(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, default=str, ensure_ascii=False) + "\n")


def expand_path(p):
    if p is None:
        return None
    return Path(os.path.expanduser(p)).resolve()


def humanize_delta(delta):
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "just now"
    if total_seconds < 60:
        return f"{total_seconds}s ago"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    remaining = minutes % 60
    if hours < 24:
        if remaining:
            return f"{hours}h {remaining}min ago"
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d {hours % 24}h ago"


def read_heartbeat(heartbeat_path):
    data = load_json(heartbeat_path)
    if data is None:
        return None, None, None
    ts = None
    for key in ("timestamp", "last_seen", "updated_at", "time"):
        if key in data:
            ts = parse_timestamp(data[key])
            if ts:
                break
    status = data.get("status", data.get("health", "UNKNOWN"))
    return ts, status, data


def get_heartbeat_path(plan):
    hb = plan.get("heartbeat", {})
    return hb.get("path")


def get_restart_command(plan):
    meta = plan.get("metadata", {})
    cmd = meta.get("process")
    if not cmd:
        return None
    location = meta.get("location")
    return {"command": cmd, "location": location, "auto_restart": meta.get("auto_restart", False)}


class Watchdog:
    def __init__(self, registry_path=None, fix_mode=False, json_output=False):
        self.registry_path = Path(registry_path) if registry_path else REGISTRY_PATH
        self.fix_mode = fix_mode
        self.json_output = json_output
        self.registry = None
        self.results = []
        self.restarts_attempted = 0
        self.alerts_sent = 0

    def load_registry(self):
        self.registry = load_json(self.registry_path)
        if self.registry is None:
            print(f"{RED}ERROR: Cannot read registry at {self.registry_path}{RESET}")
            sys.exit(1)
        return self.registry

    def check_plan(self, plan_id, plan):
        # Skip archived plans — they are intentionally dormant
        if plan.get("status") == "archived":
            return {"plan_id": plan_id, "status": "ARCHIVED", "age": None,
                    "heartbeat_path": None, "action": "skipped (archived)"}

        hb_path = get_heartbeat_path(plan)
        if not hb_path:
            return {"plan_id": plan_id, "status": "NO_HEARTBEAT", "age": None,
                    "heartbeat_path": None, "action": None}

        resolved = expand_path(hb_path)
        ts, hb_status, raw = read_heartbeat(resolved)

        if ts is None:
            return {"plan_id": plan_id, "status": "NO_DATA", "age": None,
                    "heartbeat_path": str(resolved),
                    "action": "no heartbeat file or no timestamp"}

        age = now_utc() - ts
        restart_info = get_restart_command(plan)

        if age > DEAD_THRESHOLD:
            status = "DEAD"
        elif age > STALE_THRESHOLD:
            status = "STALE"
        else:
            status = "ALIVE"

        return {
            "plan_id": plan_id, "status": status, "age": age,
            "age_human": humanize_delta(age),
            "heartbeat_path": str(resolved), "last_timestamp": ts.isoformat(),
            "hb_status": hb_status, "restart_info": restart_info, "action": None,
        }

    def load_restart_state(self):
        state = load_json(STATE_PATH) or {}
        state.setdefault('restart_history', {})
        return state

    def check_circuit_breaker(self, state, plan_id):
        now = now_utc().timestamp()
        history = state.get('restart_history', {}).get(plan_id, [])
        recent = [t for t in history if now - t < RESTART_WINDOW]
        return len(recent) >= MAX_RESTARTS, len(recent)

    def record_restart(self, state, plan_id):
        now = now_utc().timestamp()
        state.setdefault('restart_history', {}).setdefault(plan_id, []).append(now)
        state['restart_history'][plan_id] = state['restart_history'][plan_id][-10:]

    def try_restart(self, result):
        """Attempt to restart a plan.

        Returns:
            (success: bool, action_msg: str)

        success is True ONLY when subprocess.Popen actually launched a new
        process. Configuration-skips (no command / auto_restart disabled)
        return False so the circuit breaker doesn't tick on no-ops.
        """
        plan_id = result["plan_id"]
        restart_info = result.get("restart_info")

        if not restart_info or not restart_info.get("command"):
            return False, "no restart command configured"

        if not restart_info.get("auto_restart", False):
            return False, "auto_restart disabled"

        cmd = restart_info["command"]
        location = restart_info.get("location")

        if location:
            location = os.path.expanduser(location)

        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                cwd=location if location and os.path.isdir(location) else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            self.restarts_attempted += 1
            return True, f"restart triggered (pid={proc.pid}, cmd='{cmd}')"
        except Exception as e:
            return False, f"restart FAILED: {e}"

    def send_alert(self, result):
        plan_id = result["plan_id"]
        alert = {
            "timestamp": now_utc().isoformat(),
            "plan_id": plan_id,
            "status": result["status"],
            "age": result.get("age_human", "unknown"),
            "heartbeat_path": result.get("heartbeat_path"),
            "message": f"PLAN '{plan_id}' is {result['status']} (heartbeat {result.get('age_human', '?')})",
        }
        append_jsonl(ALERT_LOG, alert)
        self.alerts_sent += 1
        return f"ALERT LOGGED to {ALERT_LOG}"

    def run_checks(self):
        self.load_registry()
        plans = self.registry.get("plans", {})
        self.results = []
        self.state = self.load_restart_state()

        for plan_id, plan in plans.items():
            result = self.check_plan(plan_id, plan)

            if result["status"] == "STALE":
                if self.fix_mode:
                    is_open, count = self.check_circuit_breaker(self.state, plan_id)
                    if is_open:
                        result["action"] = f"CIRCUIT_OPEN ({count} restarts in window) — 停止重啟，需要人工介入"
                    else:
                        success, action_msg = self.try_restart(result)
                        if success:
                            self.record_restart(self.state, plan_id)
                        result["action"] = action_msg
                else:
                    result["action"] = "use --fix to attempt restart"

            elif result["status"] == "DEAD":
                alert_action = self.send_alert(result)
                if self.fix_mode:
                    is_open, count = self.check_circuit_breaker(self.state, plan_id)
                    if is_open:
                        result["action"] = f"{alert_action} | CIRCUIT_OPEN ({count} restarts in window) — 停止重啟，需要人工介入"
                    else:
                        success, restart_action = self.try_restart(result)
                        if success:
                            self.record_restart(self.state, plan_id)
                        result["action"] = f"{alert_action} | {restart_action}"
                else:
                    result["action"] = alert_action

            elif result["status"] == "NO_DATA":
                if plan.get("status") in ("active", "critical"):
                    result["action"] = "plan is active but has no heartbeat data"

            self.results.append(result)

        return self.results

    def update_watchdog_heartbeat(self):
        existing = load_json(HEARTBEAT_PATH) or {}
        heartbeat = {
            "plan_id": "watchdog",
            "name": "PLAN Registry Watchdog",
            "timestamp": now_utc().isoformat(),
            "health_score": 100,
            "status": "HEALTHY",
            "checks_performed": len(self.results),
            "restarts_attempted": self.restarts_attempted,
            "alerts_sent": self.alerts_sent,
        }
        # Preserve governance metadata added by Heartbeat Metadata Standard.
        for key in (
            "health_source",
            "external_verified",
            "trust_level",
            "confidence",
            "metadata_reviewed_by",
            "metadata_reviewed_at",
            "metadata_review_note",
        ):
            if key in existing and key not in heartbeat:
                heartbeat[key] = existing[key]
        save_json(HEARTBEAT_PATH, heartbeat)

    def save_state(self):
        state = getattr(self, 'state', {})
        state.update({
            "last_check": now_utc().isoformat(),
            "plan_statuses": {},
            "restarts_attempted": self.restarts_attempted,
            "alerts_sent": self.alerts_sent,
            "total_plans": len(self.results),
        })
        for r in self.results:
            state["plan_statuses"][r["plan_id"]] = {
                "status": r["status"],
                "age": r.get("age_human"),
                "action": r.get("action"),
            }
        save_json(STATE_PATH, state)

    def check_watchdog_self(self):
        data = load_json(HEARTBEAT_PATH)
        if data is None:
            return None, "NO_HEARTBEAT"
        ts = parse_timestamp(data.get("timestamp"))
        if ts is None:
            return None, "NO_TIMESTAMP"
        age = now_utc() - ts
        if age > WATCHDOG_DEAD_THRESHOLD:
            return age, "DEAD"
        return age, "ALIVE"

    def print_results(self):
        if self.json_output:
            self.print_json()
            return

        self_age, self_status = self.check_watchdog_self()
        print(f"\n{BOLD}{CYAN}🔍 Watchdog Check{RESET}  ({now_utc().strftime('%Y-%m-%d %H:%M:%S UTC')})")

        if self_status == "ALIVE" and self_age is not None:
            print(f"  {BOLD}watchdog (self):{RESET} ✅ ALIVE (heartbeat {humanize_delta(self_age)})")
        elif self_status == "DEAD" and self_age is not None:
            print(f"  {BOLD}watchdog (self):{RESET} 💀 DEAD (heartbeat {humanize_delta(self_age)}) — watchdog needs restart!")
        else:
            print(f"  {BOLD}watchdog (self):{RESET} ⚠️  No heartbeat found")

        print()

        for r in self.results:
            pid = r["plan_id"]
            status = r["status"]
            action = r.get("action")

            if status == "ALIVE":
                icon, color, detail = "✅", GREEN, f"heartbeat {r['age_human']}"
            elif status == "STALE":
                icon, color, detail = "⚠️", YELLOW, f"heartbeat {r['age_human']}"
            elif status == "DEAD":
                icon, color, detail = "💀", RED, f"heartbeat {r['age_human']}"
            elif status == "NO_DATA":
                icon, color, detail = "❓", YELLOW, "no heartbeat data yet"
            elif status == "NO_HEARTBEAT":
                icon, color, detail = "⬜", RESET, "no heartbeat path configured"
            else:
                icon, color, detail = "❓", RESET, "unknown"

            line = f"  {color}{icon} {pid}: {status} ({detail}){RESET}"
            if action and status not in ("ALIVE",):
                line += f" → {action}"
            print(line)

        alive = sum(1 for r in self.results if r["status"] == "ALIVE")
        stale = sum(1 for r in self.results if r["status"] == "STALE")
        dead = sum(1 for r in self.results if r["status"] == "DEAD")
        no_data = sum(1 for r in self.results if r["status"] in ("NO_DATA", "NO_HEARTBEAT"))

        print()
        print(f"  {BOLD}Summary:{RESET} {GREEN}{alive} alive{RESET}, {YELLOW}{stale} stale{RESET}, {RED}{dead} dead{RESET}, {no_data} no-data")
        if self.restarts_attempted:
            print(f"  {BOLD}Restarts:{RESET} {self.restarts_attempted} attempted")
        if self.alerts_sent:
            print(f"  {BOLD}Alerts:{RESET} {self.alerts_sent} sent → {ALERT_LOG}")
        print()

    def print_json(self):
        output = {
            "timestamp": now_utc().isoformat(),
            "self_check": {},
            "plans": [],
        }
        self_age, self_status = self.check_watchdog_self()
        output["self_check"] = {
            "status": self_status,
            "age_seconds": self_age.total_seconds() if self_age else None,
        }
        for r in self.results:
            output["plans"].append({
                "plan_id": r["plan_id"],
                "status": r["status"],
                "age_human": r.get("age_human"),
                "action": r.get("action"),
            })
        output["summary"] = {
            "restarts_attempted": self.restarts_attempted,
            "alerts_sent": self.alerts_sent,
        }
        print(json.dumps(output, indent=2, default=str, ensure_ascii=False))

    def run_once(self):
        self.run_checks()
        self.update_watchdog_heartbeat()
        self.save_state()
        self.print_results()

    def run_monitor(self):
        print(f"{BOLD}{CYAN}🐕 Watchdog Monitor started{RESET} — checking every {MONITOR_INTERVAL}s")
        print(f"   Press Ctrl+C to stop\n")

        running = True

        def handle_signal(sig, frame):
            nonlocal running
            running = False
            print(f"\n{YELLOW}Shutting down watchdog monitor...{RESET}")

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        while running:
            try:
                self.run_checks()
                self.update_watchdog_heartbeat()
                self.save_state()
                self.print_results()
            except Exception as e:
                print(f"{RED}ERROR during check: {e}{RESET}")

            for _ in range(MONITOR_INTERVAL):
                if not running:
                    break
                time.sleep(1)

        print(f"{GREEN}Watchdog monitor stopped.{RESET}")


def main():
    args = sys.argv[1:]
    fix_mode = "--fix" in args
    monitor_mode = "--monitor" in args
    json_output = "--json" in args

    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    wd = Watchdog(fix_mode=fix_mode, json_output=json_output)

    if monitor_mode:
        wd.run_monitor()
    else:
        wd.run_once()


if __name__ == "__main__":
    main()
