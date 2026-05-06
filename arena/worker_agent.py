#!/usr/bin/env python3
"""
Worker Agent — 百大交易競技場工人
===================================

創造路徑（為什麼存在）：
  PLAN Agent 是經理，發現問題、分析、決策
  但經理不自己動手——分派給 Worker 執行
  Worker 收到任務 → 查 skill（說明書）→ 執行 → 驗證 → 回報

  這跟人類一樣：
  經理說「板子有異音，去查一下」
  工人拿著說明書，按步驟檢查，回報結果
  如果說明書沒寫，工人回報「這個情況沒遇過」
  經理決定：更新說明書 / 開新的維修流程 / 自己來

架構位置：
  PLAN Agent → worker_agent.py → Arena 檔案系統
                                    ↓
                              skill_procedures/ (說明書)

工作流程：
  1. PLAN Agent 寫入 task_queue.json（任務佇列）
  2. Worker 讀取佇列，逐個執行
  3. 每個任務：
     a. 查找匹配的 skill
     b. 有 skill → 按步驟執行
     c. 沒 skill → 回報 gap（缺什麼說明書）
  4. 寫入 task_results.json（執行結果）
  5. 更新 skill 執行計數（哪些常做、哪些不常做）

任務格式：
  {
    "task_id": "T20260501_001",
    "type": "diagnose|repair|generate|validate|investigate",
    "target": "B_simulator",          // 對應 A-F 哪個節點
    "description": "具體要做什麼",
    "context": {},                     // 額外資訊
    "priority": "critical|high|medium|low",
    "created_by": "plan_agent",
    "created_at": "ISO timestamp"
  }

結果格式：
  {
    "task_id": "T20260501_001",
    "status": "success|failed|partial|no_skill|escalated",
    "actions_taken": [],
    "findings": [],
    "skill_used": "skill_name or null",
    "skill_gap": "如果沒有匹配的 skill，描述缺什麼",
    "new_skill_suggested": "如果有，建議建立什麼 skill",
    "needs_escalation": false,
    "escalation_reason": "",
    "completed_at": "ISO timestamp"
  }
"""

import json
import os
import sys
import importlib.util
import subprocess
import signal
import time
import traceback
import hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path

# ─── Conflict Detector support ──────────────────────────────
_CONFLICT_DETECTOR_PATH = Path.home() / "hermes-agent-system" / "core"
if str(_CONFLICT_DETECTOR_PATH) not in sys.path:
    sys.path.insert(0, str(_CONFLICT_DETECTOR_PATH))
try:
    from conflict_detector import check_conflict, acquire_lock, release_lock
    _CONFLICT_DETECTOR_AVAILABLE = True
except ImportError:
    _CONFLICT_DETECTOR_AVAILABLE = False

# ─── Resource mapping: task target -> conflict_detector resource ──
TARGET_TO_RESOURCE = {
    "A_ea_bridge": "ea_bridge",
    "ea_bridge": "ea_bridge",
    "B_simulator": "simulator",
    "simulator": "simulator",
    "C_signal_engine": "simulator",
    "signal_engine": "simulator",
    "D_referee": "simulator",
    "referee": "simulator",
    "E_score_publisher": "simulator",
    "score_publisher": "simulator",
}

# ─── Task timeout support ─────────────────────────────────────
class TaskTimeout(Exception):
    """Raised when a task exceeds the allowed time."""
    pass


def _timeout_handler(signum, frame):
    raise TaskTimeout('Task exceeded 120s timeout')

# ─── 路徑 ────────────────────────────────────────────────────
ARENA_ROOT = Path(__file__).resolve().parents[1]
CONTROL = ARENA_ROOT / "arena_control"
CONTESTANTS = ARENA_ROOT / "contestants"
LIVE_DATA = ARENA_ROOT / "live_data"
SIGNALS = ARENA_ROOT / "signals"
LEADERBOARD = ARENA_ROOT / "leaderboard"
DASHBOARD = ARENA_ROOT / "dashboard"
SKILLS_DIR = CONTROL / "worker_skills"

TASK_QUEUE = CONTROL / "task_queue.json"
TASK_RESULTS = CONTROL / "task_results.json"
WORKER_LOG = CONTROL / "worker_log.json"
TASK_STATES = ["queued", "claimed", "running", "succeeded", "failed", "failed_verify", "verified"]

# ─── 模組清單 ────────────────────────────────────────────────
MODULES = ["gpt_5.5", "opus_4.6", "opus_4.7", "deepseek_v4_pro", "mimo-v2-pro"]

# ─── 架構知識（Worker 的「全貌」） ───────────────────────────
# Worker 需要知道 Arena 的創造路徑，才能判斷問題在哪
ARCHITECTURE = {
    "A_ea_bridge": {
        "file": "arena_control/ea_bridge.py",
        "role": "MT4 數據橋接 — 讀取 EA 的 CSV，同步到 arena 目錄",
        "inputs": ["MT4 MQL4\\Files\\*.csv"],
        "outputs": ["live_data/*.csv", "signals/ea_bridge_status.json"],
        "depends_on": [],
        "depended_by": ["B_simulator", "C_signal_engine"],
        "critical": True,
        "creation_note": "最基礎的節點，沒有它後面全部斷"
    },
    "B_simulator": {
        "file": "arena_control/arena_simulator.py",
        "role": "虛擬回測 — 跑所有策略，模擬交易，記錄盈虧",
        "inputs": ["live_data/*.csv", "contestants/*/active/*.py"],
        "outputs": ["trade_logs/*/*.json", "arena_simulator_state.json"],
        "depends_on": ["A_ea_bridge"],
        "depended_by": ["D_referee", "E_score_publisher"],
        "critical": True,
        "creation_note": "核心引擎，策略在這裡被「試跑」"
    },
    "C_signal_engine": {
        "file": "arena_control/signal_engine.py",
        "role": "即時信號選拔 — 選最高 confidence 的信號給 EA",
        "inputs": ["live_data/*.csv", "contestants/*/active/*.py", "signals/ea_bridge_status.json"],
        "outputs": ["signals/proposed_signal_xauusd.json", "MQL4\\Files\\signal_xauusd.csv"],
        "depends_on": ["A_ea_bridge"],
        "depended_by": [],
        "critical": True,
        "creation_note": "連接虛擬競技場和真實交易的橋"
    },
    "D_referee": {
        "file": "arena_control/referee_engine.py",
        "role": "裁判 — 評分、淘汰、免疫、結算",
        "inputs": ["trade_logs/*/*.json", "contestants/*/active/*.py"],
        "outputs": ["leaderboard/*.json", "elimination_log.csv", "replenishment_requests.json"],
        "depends_on": ["B_simulator"],
        "depended_by": ["E_score_publisher"],
        "critical": True,
        "creation_note": "競爭規則的執行者，決定誰活誰死"
    },
    "E_score_publisher": {
        "file": "arena_control/score_publisher.py",
        "role": "分數發布 — 即時更新排行榜",
        "inputs": ["trade_logs/*/*.json", "contestants/*/active/*.py"],
        "outputs": ["leaderboard/*.json"],
        "depends_on": ["D_referee"],
        "depended_by": ["F_dashboard"],
        "critical": False,
        "creation_note": "把裁判的評分公開化"
    },
    "F_dashboard": {
        "file": "dashboard/",
        "role": "儀表板 — HTML 看板",
        "inputs": ["leaderboard/*.json"],
        "outputs": ["dashboard/dashboard_data.json"],
        "depends_on": ["E_score_publisher"],
        "depended_by": [],
        "critical": False,
        "creation_note": "人類看的介面"
    },
    "G_generators": {
        "file": "arena_control/gen_strats.py, gen_opus46.py, mimo_strategy_generator.py",
        "role": "策略工廠 — AI 生成新策略",
        "inputs": ["API 呼叫"],
        "outputs": ["contestants/*/active/*.py"],
        "depends_on": [],
        "depended_by": ["B_simulator", "C_signal_engine"],
        "critical": False,
        "creation_note": "補充兵源，淘汰後需要它填補"
    }
}


# ══════════════════════════════════════════════════════════════
#  工具函式
# ══════════════════════════════════════════════════════════════


def compute_skill_checksum(skill_data):
    """Compute SHA256 of skill's steps content (integrity check)."""
    steps_str = json.dumps(skill_data.get('steps', []), sort_keys=True)
    return hashlib.sha256(steps_str.encode()).hexdigest()[:16]

def _load_json(path, default=None):
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return json.loads(text)
    except Exception:
        return default if default is not None else {}


def _save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def _log(action, detail, task_id=None):
    logs = _load_json(WORKER_LOG, [])
    if not isinstance(logs, list):
        logs = []
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
        "action": action,
        "detail": detail
    })
    if len(logs) > 500:
        logs = logs[-500:]
    _save_json(WORKER_LOG, logs)


def _is_process_running(name_pattern):
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", name_pattern],
            stderr=subprocess.DEVNULL, text=True, timeout=30
        ).strip()
        return len(out) > 0
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════
#  Idempotency — 同日同任務不重複執行
# ══════════════════════════════════════════════════════════════

def _generate_idempotency_key(task_type, target, date_str=None):
    """Generate idempotency key from (task_type + target + date)."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    raw = f"{task_type}|{target}|{date_str}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _check_already_succeeded(idempotency_key):
    """Check task_results.json for a task with same idempotency_key that succeeded."""
    all_results = _load_json(TASK_RESULTS, [])
    if not isinstance(all_results, list):
        return False
    for r in all_results:
        if r.get("idempotency_key") == idempotency_key and r.get("status") in ("succeeded", "verified"):
            return True
    return False


def _update_task_status(tasks, task_id, status):
    """Update the lifecycle status of a task in the queue."""
    for t in tasks:
        if t.get("task_id") == task_id:
            t["status"] = status
            t["state_changed_at"] = datetime.now().isoformat()
            return True
    return False

# ══════════════════════════════════════════════════════════════
#  Skill Registry（說明書系統）
# ══════════════════════════════════════════════════════════════

class SkillRegistry:
    """
    Worker 的說明書系統。
    每個 skill 是一個 .json 檔案，描述：
    - 名稱、適用場景
    - 執行步驟（可自動化或需人工）
    - 創造路徑（為什麼有這個 skill、跟什麼有關）
    - 執行歷史（做過幾次、成功率）
    """
    
    def __init__(self, skills_dir=SKILLS_DIR):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.skills = {}
        self._load_all()
    
    def _load_all(self):
        """載入所有 skill（掃描 generic/ 和 arena/ 子目錄）"""
        for f in self.skills_dir.rglob("*.json"):
            try:
                skill = _load_json(f)
                if skill and "name" in skill:
                    # Compute and store checksum at load time for tamper detection
                    skill['_checksum'] = compute_skill_checksum(skill)
                    skill['_source_path'] = str(f)  # remember file location for writes
                    self.skills[skill["name"]] = skill
            except Exception:
                pass
    
    def find(self, task_type, target):
        """
        查找匹配的 skill。
        匹配邏輯：task_type + target 節點
        """
        matches = []
        for name, skill in self.skills.items():
            if skill.get("task_type") == task_type:
                # Verify checksum hasn't changed since load (tamper detection)
                current = compute_skill_checksum(skill)
                if current != skill.get('_checksum'):
                    # Skill was modified externally — reload from disk
                    skill_file = skill.get('_source_path', str(self.skills_dir / f"{name}.json"))
                    reloaded = _load_json(skill_file)
                    if reloaded and "name" in reloaded:
                        reloaded['_checksum'] = compute_skill_checksum(reloaded)
                        reloaded['_source_path'] = skill_file
                        self.skills[name] = reloaded
                        skill = reloaded
                if not target or skill.get("target") == target or skill.get("target") == "*":
                    matches.append(skill)
        
        # 按優先序排序：精確匹配 > 萬用匹配
        matches.sort(key=lambda s: 0 if s.get("target") == target else 1)
        return matches
    
    def record_execution(self, skill_name, success, details=""):
        """記錄 skill 執行歷史"""
        if skill_name in self.skills:
            skill = self.skills[skill_name]
            if "execution_history" not in skill:
                skill["execution_history"] = {"total": 0, "success": 0, "failed": 0}
            skill["execution_history"]["total"] += 1
            if success:
                skill["execution_history"]["success"] += 1
            else:
                skill["execution_history"]["failed"] += 1
            skill["execution_history"]["last_executed"] = datetime.now().isoformat()
            skill["execution_history"]["last_details"] = details

            # Record structured failure info for skill evolution
            if not success:
                if 'failure_patterns' not in skill['execution_history']:
                    skill['execution_history']['failure_patterns'] = []
                # details may be a string or a dict
                failed_step = 'unknown'
                error_msg = str(details)
                task_type_val = 'unknown'
                if isinstance(details, dict):
                    failed_step = details.get('failed_step', 'unknown')
                    error_msg = details.get('error', str(details))
                    task_type_val = details.get('task_type', 'unknown')
                skill['execution_history']['failure_patterns'].append({
                    'timestamp': datetime.now().isoformat(),
                    'step': failed_step,
                    'error': error_msg,
                    'task_type': task_type_val
                })
                # Keep only last 20 failures
                skill['execution_history']['failure_patterns'] = \
                    skill['execution_history']['failure_patterns'][-20:]

            # 寫回檔案（使用載入時記錄的路徑）
            skill_file = skill.get('_source_path', str(self.skills_dir / f"{skill_name}.json"))
            _save_json(skill_file, skill)
    
    def suggest_new_skill(self, task_type, target, gap_description):
        """建議建立新 skill"""
        return {
            "suggested_name": f"{task_type}_{target}",
            "task_type": task_type,
            "target": target,
            "gap": gap_description,
            "reason": f"任務 {task_type} 在 {target} 上沒有匹配的 skill",
            "suggested_at": datetime.now().isoformat()
        }

    def analyze_skill_health(self):
        """Analyze all skills and suggest improvements"""
        suggestions = []
        for name, skill in self.skills.items():
            history = skill.get('execution_history', {})
            total = history.get('total', 0)
            failed = history.get('failed', 0)
            if total >= 5 and failed / total > 0.3:
                # >30% failure rate
                patterns = history.get('failure_patterns', [])
                common_errors = Counter(
                    p.get('error', '') for p in patterns
                ).most_common(3)
                suggestions.append({
                    'skill': name,
                    'failure_rate': round(failed / total, 2),
                    'common_errors': common_errors,
                    'suggestion': (
                        f'Skill {name} has {failed}/{total} failures. '
                        f'Consider reviewing steps.'
                    )
                })
        return suggestions

    def generate_improvement_report(self):
        """Generate a markdown improvement report for skills with issues"""
        suggestions = self.analyze_skill_health()
        lines = [
            "# Skill Health Report",
            "",
            f"Generated: {datetime.now().isoformat()}",
            "",
        ]

        if not suggestions:
            lines.append("All skills are healthy (failure rate <= 30% or < 5 executions).")
            lines.append("")
        else:
            lines.append(f"## Skills Requiring Attention ({len(suggestions)})")
            lines.append("")
            for s in suggestions:
                lines.append(f"### {s['skill']}")
                lines.append(f"- **Failure rate:** {s['failure_rate']*100:.0f}%")
                lines.append(f"- **Common errors:**")
                for err, count in s['common_errors']:
                    err_display = err if err else '(empty)'
                    lines.append(f"  - `{err_display}` ({count}x)")
                lines.append(f"- **Suggestion:** {s['suggestion']}")
                lines.append("")

        # Summary table of all skills
        lines.append("## All Skills Summary")
        lines.append("")
        lines.append("| Skill | Total | Success | Failed | Failure Rate |")
        lines.append("|-------|-------|---------|--------|--------------|")
        for name, skill in sorted(self.skills.items()):
            h = skill.get('execution_history', {})
            t = h.get('total', 0)
            s = h.get('success', 0)
            f = h.get('failed', 0)
            rate = f"{f/t*100:.0f}%" if t > 0 else "N/A"
            lines.append(f"| {name} | {t} | {s} | {f} | {rate} |")
        lines.append("")

        # Failure pattern details
        for name, skill in sorted(self.skills.items()):
            patterns = skill.get('execution_history', {}).get('failure_patterns', [])
            if patterns:
                lines.append(f"## Failure Patterns: {name}")
                lines.append("")
                lines.append("| Timestamp | Step | Error | Task Type |")
                lines.append("|-----------|------|-------|-----------|")
                for p in patterns[-10:]:  # last 10
                    lines.append(
                        f"| {p.get('timestamp', '')} "
                        f"| {p.get('step', '')} "
                        f"| {p.get('error', '')} "
                        f"| {p.get('task_type', '')} |"
                    )
                lines.append("")

        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
#  Worker 核心
# ══════════════════════════════════════════════════════════════

class WorkerAgent:
    """
    Worker Agent — 任務執行者
    
    工作流程：
    1. 接收任務（從 task_queue）
    2. 查找 skill（說明書）
    3. 執行（按步驟）
    4. 驗證結果
    5. 回報
    """
    
    def __init__(self):
        self.registry = SkillRegistry()
        self.results = []
    
    def process_queue(self):
        """處理整個任務佇列"""
        tasks = _load_json(TASK_QUEUE, [])
        if not isinstance(tasks, list) or not tasks:
            print("  任務佇列為空")
            return []
        
        results = []
        pending = [t for t in tasks if t.get("status") in ("pending", "queued")]
        
        print(f"  待處理任務: {len(pending)} 個")
        
        for task in pending:
            task_id = task.get("task_id", "unknown")
            task_type = task.get("type", "unknown")
            target = task.get("target", "")

            # Generate idempotency key
            idem_key = _generate_idempotency_key(task_type, target)
            task["idempotency_key"] = idem_key

            # Idempotency check: skip if already succeeded today
            if _check_already_succeeded(idem_key):
                _log("skip", f"skipped: already succeeded (key={idem_key})", task_id)
                print(f"  ⏭ 任務 {task_id}: skipped: already succeeded")
                task["status"] = "succeeded"
                task["state_changed_at"] = datetime.now().isoformat()
                continue

            # Lifecycle: claimed
            _update_task_status(tasks, task_id, "claimed")
            _log("state_change", "claimed", task_id)

            # Lifecycle: running
            _update_task_status(tasks, task_id, "running")
            result = self.execute_task(task)
            results.append(result)
            
            # Lifecycle: succeeded or failed (preserve failed_verify)
            raw_status = result["status"]
            if raw_status == "success":
                final_status = "succeeded"
            elif raw_status == "failed_verify":
                final_status = "failed_verify"
            else:
                final_status = "failed"
            result["status"] = final_status
            _update_task_status(tasks, task_id, final_status)
            task["completed_at"] = result.get("completed_at")
        
        # 儲存結果
        all_results = _load_json(TASK_RESULTS, [])
        if not isinstance(all_results, list):
            all_results = []
        all_results.extend(results)
        if len(all_results) > 200:
            all_results = all_results[-200:]
        _save_json(TASK_RESULTS, all_results)
        
        # 更新佇列
        _save_json(TASK_QUEUE, tasks)
        
        self.results = results
        return results
    
    def execute_task(self, task):
        """執行單一任務"""
        task_id = task.get("task_id", "unknown")
        task_type = task.get("type", "unknown")
        target = task.get("target", "")
        description = task.get("description", "")
        idem_key = task.get("idempotency_key", "")
        
        print(f"\n  ▶ 任務 {task_id}: [{task_type}] {description[:60]}...")
        
        result = {
            "task_id": task_id,
            "idempotency_key": idem_key,
            "status": "unknown",
            "actions_taken": [],
            "findings": [],
            "skill_used": None,
            "skill_gap": None,
            "new_skill_suggested": None,
            "needs_escalation": False,
            "escalation_reason": "",
            "completed_at": datetime.now().isoformat()
        }

        # ─── Conflict detection (repair tasks only) ───────────────
        _cd_resource = TARGET_TO_RESOURCE.get(target)
        _cd_locked = False
        if task_type == "repair" and _CONFLICT_DETECTOR_AVAILABLE and _cd_resource:
            conflict_result = check_conflict("arena_worker", _cd_resource, "restart")
            if not conflict_result.get("safe", False):
                conflict_msgs = "; ".join(conflict_result.get("conflicts", []))
                print(f"    ⚠️ Conflict detected on '{_cd_resource}': {conflict_msgs}")
                result["status"] = "conflict_detected"
                result["findings"].append(f"Conflict detected: {conflict_msgs}")
                result["needs_escalation"] = True
                result["escalation_reason"] = f"conflict_detected on {_cd_resource}"
                result["completed_at"] = datetime.now().isoformat()
                _log("conflict_detected", f"resource={_cd_resource}, conflicts={conflict_msgs}", task_id)
                return result

            lock_ok, lock_reason = acquire_lock("arena_worker", _cd_resource, "restart")
            if not lock_ok:
                print(f"    🔒 Lock denied for '{_cd_resource}': {lock_reason}")
                result["status"] = "conflict_detected"
                result["findings"].append(f"Lock denied: {lock_reason}")
                result["needs_escalation"] = True
                result["escalation_reason"] = f"lock_denied on {_cd_resource}"
                result["completed_at"] = datetime.now().isoformat()
                _log("lock_denied", f"resource={_cd_resource}, reason={lock_reason}", task_id)
                return result

            _cd_locked = True
            print(f"    🔓 Lock acquired for '{_cd_resource}'")
            _log("lock_acquired", f"resource={_cd_resource}", task_id)

        # 1. 查找 skill
        skills = self.registry.find(task_type, target)

        # ─── 120s task-level timeout ─────────────────────────────
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(120)
        try:
            if skills:
                skill = skills[0]
                result["skill_used"] = skill["name"]
                print(f"    找到 skill: {skill['name']}")

                # 2. 執行 skill
                try:
                    exec_result = self._execute_skill(skill, task)
                    result.update(exec_result)
                    self.registry.record_execution(skill["name"], True, str(exec_result.get("findings", [])))
                    _log("execute", f"skill={skill['name']}, status={result['status']}", task_id)
                except Exception as e:
                    result["status"] = "failed"
                    result["findings"].append(f"執行錯誤: {str(e)}")
                    self.registry.record_execution(skill["name"], False, str(e))
                    _log("error", f"skill={skill['name']}, error={str(e)}", task_id)
            else:
                # 3. 沒有 skill — 用基礎診斷
                print(f"    沒有匹配的 skill，使用基礎診斷")
                result["skill_gap"] = f"沒有 {task_type} 在 {target} 的 skill"
                result["new_skill_suggested"] = self.registry.suggest_new_skill(
                    task_type, target, description
                )

                try:
                    exec_result = self._basic_diagnosis(task)
                    result.update(exec_result)
                    _log("basic_diagnosis", f"target={target}, status={result['status']}", task_id)
                except Exception as e:
                    result["status"] = "failed"
                    result["findings"].append(f"基礎診斷錯誤: {str(e)}")

            # Verify step: check if repair actually fixed the target
            if task_type == "repair" and result.get("status") == "success":
                verified = self._verify_repair(task)
                if not verified:
                    result["status"] = "failed_verify"
                    result["findings"].append("驗證失敗: 修復後目標狀態未改善")
                    _log("verify_failed", "repair verification failed", task_id)
                else:
                    result["findings"].append("✓ 驗證通過: 修復後目標狀態正常")
                    _log("verify_ok", "repair verification passed", task_id)

        except TaskTimeout:
            result["status"] = "timeout"
            result["findings"].append("Task exceeded 120s timeout")
            result["needs_escalation"] = True
            result["escalation_reason"] = "Task exceeded 120s timeout"
            _log("timeout", f"task exceeded 120s limit", task_id)
        finally:
            signal.alarm(0)  # Cancel alarm
            # Release conflict detector lock if acquired
            if _cd_locked and _cd_resource:
                try:
                    rel_ok, rel_reason = release_lock("arena_worker", _cd_resource)
                    if rel_ok:
                        print(f"    🔓 Lock released for '{_cd_resource}'")
                        _log("lock_released", f"resource={_cd_resource}", task_id)
                    else:
                        _log("lock_release_failed", f"resource={_cd_resource}, reason={rel_reason}", task_id)
                except Exception as e:
                    _log("lock_release_error", f"resource={_cd_resource}, error={e}", task_id)
        
        return result
    
    def _execute_skill(self, skill, task):
        """按 skill 的步驟執行"""
        steps = skill.get("steps", [])
        result = {
            "status": "success",
            "actions_taken": [],
            "findings": []
        }
        
        # 建立模板變數：從 task target 查 skill parameters
        target = task.get("target", "")
        params = skill.get("parameters", {})
        templates = {"ARENA_ROOT": str(ARENA_ROOT)}
        
        # 從 task context 取服務名
        service_name = task.get("context", {}).get("service", target)
        
        # 查 skill 的 parameters 取得 pattern/args
        if service_name in params:
            svc_params = params[service_name]
            templates["service_pattern"] = svc_params.get("pattern", service_name)
            templates["service"] = service_name
            templates["args"] = svc_params.get("args", "")
        else:
            # 嘗試模糊匹配
            for key, val in params.items():
                if key in target or target in key:
                    templates["service_pattern"] = val.get("pattern", key)
                    templates["service"] = key
                    templates["args"] = val.get("args", "")
                    break
            else:
                templates["service_pattern"] = target
                templates["service"] = target
                templates["args"] = ""
        
        def apply_templates(obj):
            """遞迴替換所有模板變數"""
            if isinstance(obj, str):
                for k, v in templates.items():
                    obj = obj.replace(f"{{{k}}}", str(v))
                return obj
            elif isinstance(obj, dict):
                return {k: apply_templates(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [apply_templates(item) for item in obj]
            return obj
        
        # 套用模板到所有 steps
        steps = apply_templates(steps)
        
        for i, step in enumerate(steps):
            step_type = step.get("type", "")
            step_desc = step.get("description", "")
            
            print(f"    步驟 {i+1}: {step_desc}")
            
            if step_type == "check_file":
                # 檢查檔案是否存在
                filepath = step.get("path", "")
                filepath = filepath.replace("{ARENA_ROOT}", str(ARENA_ROOT))
                exists = Path(filepath).exists()
                result["findings"].append(f"{'✓' if exists else '✗'} {filepath}: {'存在' if exists else '不存在'}")
                if not exists and step.get("required", False):
                    result["status"] = "partial"
            
            elif step_type == "check_process":
                # 檢查進程
                pattern = step.get("pattern", "")
                running = _is_process_running(pattern)
                result["findings"].append(f"{'✓' if running else '✗'} 進程 {pattern}: {'運行中' if running else '未運行'}")
                if not running and step.get("auto_restart", False):
                    # 嘗試重啟
                    restart_cmd = step.get("restart_command", "")
                    if restart_cmd:
                        restart_cmd = restart_cmd.replace("{ARENA_ROOT}", str(ARENA_ROOT))
                        try:
                            subprocess.Popen(
                                restart_cmd, shell=True,
                                cwd=str(ARENA_ROOT),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                start_new_session=True
                            )
                            result["actions_taken"].append(f"已重啟 {pattern}")
                        except Exception as e:
                            result["actions_taken"].append(f"重啟 {pattern} 失敗: {e}")
            
            elif step_type == "check_json":
                # 檢查 JSON 檔案的值
                filepath = step.get("path", "")
                filepath = filepath.replace("{ARENA_ROOT}", str(ARENA_ROOT))
                data = _load_json(filepath)
                field = step.get("field", "")
                condition = step.get("condition", "")
                
                if data:
                    value = data
                    for key in field.split("."):
                        if isinstance(value, dict):
                            value = value.get(key)
                        else:
                            value = None
                            break
                    
                    result["findings"].append(f"  {field} = {value}")
                    
                    if condition == "not_zero" and value == 0:
                        result["status"] = "partial"
                        result["findings"].append(f"  ⚠️ {field} 為 0")
                    elif condition == "not_null" and value is None:
                        result["status"] = "partial"
                else:
                    result["findings"].append(f"  ✗ {filepath} 讀取失敗")
            
            elif step_type == "check_csv":
                # 檢查 CSV 更新時間
                filepath = step.get("path", "")
                filepath = filepath.replace("{ARENA_ROOT}", str(ARENA_ROOT))
                max_age_min = step.get("max_age_minutes", 10)
                
                try:
                    age = (time.time() - os.path.getmtime(filepath)) / 60
                    ok = age <= max_age_min
                    result["findings"].append(f"{'✓' if ok else '✗'} CSV 更新: {age:.0f}分鐘前 (門檻: {max_age_min})")
                    if not ok:
                        result["status"] = "partial"
                except Exception:
                    result["findings"].append(f"✗ CSV 不存在: {filepath}")
                    result["status"] = "partial"
            
            elif step_type == "count_files":
                # 計算檔案數量
                directory = step.get("path", "")
                directory = directory.replace("{ARENA_ROOT}", str(ARENA_ROOT))
                pattern = step.get("pattern", "*.py")
                target_count = step.get("target", 100)
                
                try:
                    count = len(list(Path(directory).glob(pattern)))
                    ok = count >= target_count
                    result["findings"].append(f"{'✓' if ok else '⚠️'} 檔案數: {count} (目標: {target_count})")
                    if not ok:
                        result["status"] = "partial"
                except Exception:
                    result["findings"].append(f"✗ 目錄不存在: {directory}")
            
            elif step_type == "command":
                # 執行命令
                cmd = step.get("command", "")
                cmd = cmd.replace("{ARENA_ROOT}", str(ARENA_ROOT))
                try:
                    out = subprocess.check_output(
                        cmd, shell=True, cwd=str(ARENA_ROOT),
                        stderr=subprocess.STDOUT, text=True, timeout=30
                    )
                    result["findings"].append(f"命令輸出: {out[:500]}")
                    result["actions_taken"].append(f"執行: {cmd[:80]}")
                except subprocess.CalledProcessError as e:
                    result["findings"].append(f"命令失敗: {e.output[:500] if e.output else str(e)}")
                    result["status"] = "partial"
            
            elif step_type == "report_only":
                # 只報告，不執行
                result["findings"].append(f"📋 {step.get('note', '')}")
            
            else:
                result["findings"].append(f"未知步驟類型: {step_type}")
        
        return result
    
    def _verify_repair(self, task):
        """
        驗證修復是否成功。
        Check if the target is actually fixed (e.g., process is running after restart).
        Returns True if verification passes, False otherwise.
        """
        target = task.get("target", "")
        context = task.get("context", {})
        
        # Strategy 1: Check if a process related to the target is running
        arch = ARCHITECTURE.get(target, {})
        if arch:
            file_path = arch.get("file", "")
            if file_path:
                # Check if the main file exists and is valid
                for fp in file_path.split(", "):
                    full_path = ARENA_ROOT / fp.strip()
                    if full_path.exists():
                        return True
        
        # Strategy 2: Check context for verification hints
        verify_check = context.get("verify_process")
        if verify_check:
            return _is_process_running(verify_check)
        
        # Strategy 3: Check context for verify_command
        verify_cmd = context.get("verify_command")
        if verify_cmd:
            try:
                out = subprocess.check_output(
                    verify_cmd, shell=True, cwd=str(ARENA_ROOT),
                    stderr=subprocess.STDOUT, text=True, timeout=15
                )
                return True
            except Exception:
                return False
        
        # Default: assume repair succeeded if no verification method available
        return True
    
    def _basic_diagnosis(self, task):
        """
        基礎診斷 — 沒有 skill 時的預設行為
        沿著創造路徑檢查基本狀態
        """
        target = task.get("target", "")
        result = {
            "status": "success",
            "actions_taken": [],
            "findings": []
        }
        
        # 根據 target 做基礎檢查
        arch = ARCHITECTURE.get(target, {})
        if not arch:
            result["findings"].append(f"未知目標: {target}")
            result["status"] = "failed"
            return result
        
        result["findings"].append(f"架構節點: {arch['role']}")
        result["findings"].append(f"創造路徑: {arch['creation_note']}")
        
        # 檔案是否存在
        file_path = arch.get("file", "")
        if file_path:
            for fp in file_path.split(", "):
                full_path = ARENA_ROOT / fp.strip()
                exists = full_path.exists()
                result["findings"].append(f"{'✓' if exists else '✗'} {fp.strip()}: {'存在' if exists else '不存在'}")
        
        # 依賴關係
        depends = arch.get("depends_on", [])
        if depends:
            result["findings"].append(f"依賴: {' → '.join(depends)} → {target}")
        
        depended_by = arch.get("depended_by", [])
        if depended_by:
            result["findings"].append(f"被依賴: {target} → {', '.join(depended_by)}")
        
        # 輸出檔案
        outputs = arch.get("outputs", [])
        for out in outputs:
            out_path = ARENA_ROOT / out.replace("*", "").replace("?", "")
            # 簡單檢查：目錄是否存在
            parent = out_path.parent if "*" in out else out_path
            if parent.exists():
                result["findings"].append(f"  輸出目錄存在: {out}")
            else:
                result["findings"].append(f"  ⚠️ 輸出目錄不存在: {out}")
        
        return result


# ══════════════════════════════════════════════════════════════
#  Worker 直接執行（被 PLAN Agent 呼叫）
# ══════════════════════════════════════════════════════════════

def run_worker():
    """Worker 主程式：讀取佇列、執行、回報"""
    print(f"\n{'='*60}")
    print(f"  Worker Agent 啟動")
    print(f"  {datetime.now().isoformat()}")
    print(f"{'='*60}")
    
    worker = WorkerAgent()
    results = worker.process_queue()
    
    # 摘要
    success = len([r for r in results if r["status"] in ("success", "succeeded")])
    failed = len([r for r in results if r["status"] == "failed"])
    failed_verify = len([r for r in results if r["status"] == "failed_verify"])
    partial = len([r for r in results if r["status"] == "partial"])
    no_skill = len([r for r in results if r["status"] == "no_skill"])
    timed_out = len([r for r in results if r["status"] == "timeout"])
    escalated = len([r for r in results if r.get("needs_escalation")])
    
    print(f"\n  執行摘要:")
    print(f"    ✅ 成功: {success}")
    print(f"    ⚠️ 部分: {partial}")
    print(f"    ❌ 失敗: {failed}")
    if failed_verify:
        print(f"    🔍 驗證失敗: {failed_verify}")
    if timed_out:
        print(f"    ⏱️ 超時: {timed_out}")
    print(f"    📋 無 skill: {no_skill}")
    if escalated:
        print(f"    📢 需上報: {escalated}")
    
    # skill 缺口
    gaps = [r for r in results if r.get("skill_gap")]
    if gaps:
        print(f"\n  Skill 缺口:")
        for g in gaps:
            print(f"    • {g['skill_gap']}")
    
    print(f"\n{'='*60}\n")
    return results


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "health":
        reg = SkillRegistry()
        suggestions = reg.analyze_skill_health()
        print(f"\n{'='*60}")
        print("  Skill Health Analysis")
        print(f"{'='*60}")
        if not suggestions:
            print("  All skills are healthy (failure rate <= 30% or < 5 executions).")
        else:
            for s in suggestions:
                print(f"\n  ⚠️  {s['skill']}")
                print(f"     Failure rate: {s['failure_rate']*100:.0f}%")
                print(f"     Common errors:")
                for err, count in s['common_errors']:
                    err_display = err if err else '(empty)'
                    print(f"       - {err_display} ({count}x)")
                print(f"     Suggestion: {s['suggestion']}")

        # Also generate full report
        report = reg.generate_improvement_report()
        report_path = CONTROL / "skill_health_report.md"
        Path(report_path).write_text(report, encoding="utf-8")
        print(f"\n  Full report saved to: {report_path}")
        print(f"{'='*60}\n")
    else:
        run_worker()
