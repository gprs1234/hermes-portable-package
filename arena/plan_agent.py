#!/usr/bin/env python3
"""
PLAN Agent — Autonomous Manager for 百大交易競技場 (Trading Arena)

Patrols the full A→B→C→D→E→F data flow, auto-fixes simple issues,
dispatches tasks to Worker Agent, writes heartbeat, checks for Hermes
commands, and generates reports.

Usage:
    python3 plan_agent.py [--fix] [--dispatch] [--report-only]

Exit codes: 0 = healthy, 1 = HIGH issues, 2 = CRITICAL issues
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import glob as globmod
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


# ---------------------------------------------------------------------------
# State Machine
# ---------------------------------------------------------------------------
class PlanState(Enum):
    """Lifecycle states for the PLAN Agent patrol cycle."""
    INIT = "INIT"                   # Starting up
    HEALTH_CHECK = "HEALTH_CHECK"   # Checking services
    DIAGNOSE = "DIAGNOSE"           # Analyzing issues
    AUTO_REPAIR = "AUTO_REPAIR"     # Applying fixes
    DISPATCH = "DISPATCH"           # Sending tasks to Worker
    VERIFY = "VERIFY"               # Confirming fixes worked
    REPORT = "REPORT"               # Writing heartbeat + report
    IDLE = "IDLE"                   # Waiting for next cycle
    ESCALATE = "ESCALATE"           # Needs human attention


# State transition log — accumulates state names for this patrol
_state_log: List[str] = []


def _set_state(state: PlanState) -> None:
    """Transition to a new state, log the transition, and update state_log."""
    _state_log.append(state.value)
    arrow_chain = " -> ".join(_state_log)
    print(f"  [STATE] {state.value}  (flow: {arrow_chain})")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ARENA_ROOT = Path(__file__).resolve().parents[1]  # arena/
CONTROL = ARENA_ROOT / "arena_control"
CONTESTANTS = ARENA_ROOT / "contestants"
LIVE_DATA = ARENA_ROOT / "live_data"
SIGNALS = ARENA_ROOT / "signals"
LEADERBOARD = ARENA_ROOT / "leaderboard"
DASHBOARD = ARENA_ROOT / "dashboard"
LOGS = ARENA_ROOT / "logs"

MODULES = ["gpt_5.5", "opus_4.6", "opus_4.7", "deepseek_v4_pro", "mimo-v2-pro"]
TARGET_PER_MODULE = 100

# EA is ECMARKET — it should be running
EA_EXPECTED_OFFLINE = False

# Freshness thresholds (seconds)
CSV_FRESHNESS_THRESHOLD = 300      # 5 min for EA CSV
SIGNAL_FRESHNESS_THRESHOLD = 600   # 10 min for signals
LEADERBOARD_FRESHNESS_THRESHOLD = 600  # 10 min for leaderboard
DASHBOARD_FRESHNESS_THRESHOLD = 600    # 10 min for dashboard

# Issue severity levels
SEV_INFO = "INFO"
SEV_LOW = "LOW"
SEV_MEDIUM = "MEDIUM"
SEV_HIGH = "HIGH"
SEV_CRITICAL = "CRITICAL"

# Scripts in arena_control
EA_BRIDGE_SCRIPT = CONTROL / "ea_bridge.py"
SIMULATOR_SCRIPT = CONTROL / "arena_simulator.py"
SIGNAL_ENGINE_SCRIPT = CONTROL / "signal_engine.py"
REFEREE_SCRIPT = CONTROL / "referee_engine.py"
SCORE_PUBLISHER_SCRIPT = CONTROL / "score_publisher.py"
WORKER_SCRIPT = CONTROL / "worker_agent.py"

# Heartbeat / command / task files
HEARTBEAT_FILE = CONTROL / "plan_heartbeat.json"
COMMAND_FILE = CONTROL / "plan_command.json"
TASK_QUEUE_FILE = CONTROL / "task_queue.json"
REPORT_FILE = CONTROL / "plan_agent_report.json"
REPLENISH_FILE = LIVE_DATA / "replenishment_requests.json"
DASHBOARD_DATA_FILE = DASHBOARD / "dashboard_data.json"

# ---------------------------------------------------------------------------
# ISSUE_TO_TASK mapping — common issues → worker tasks
# ---------------------------------------------------------------------------
ISSUE_TO_TASK = {
    "EA_BRIDGE_DOWN": {"action": "restart_process", "script": str(EA_BRIDGE_SCRIPT), "priority": "critical"},
    "EA_BRIDGE_STALE_CSV": {"action": "restart_process", "script": str(EA_BRIDGE_SCRIPT), "priority": "high"},
    "SCORE_PUBLISHER_DOWN": {"action": "restart_process", "script": str(SCORE_PUBLISHER_SCRIPT), "priority": "high"},
    "SIMULATOR_DOWN": {"action": "restart_process", "script": str(SIMULATOR_SCRIPT), "priority": "high"},
    "SIGNAL_ENGINE_DOWN": {"action": "restart_process", "script": str(SIGNAL_ENGINE_SCRIPT), "priority": "high"},
    "REFEREE_DOWN": {"action": "restart_process", "script": str(REFEREE_SCRIPT), "priority": "high"},
    "STRATEGY_COUNT_LOW": {"action": "generate_strategies", "priority": "medium"},
    "LEADERBOARD_STALE": {"action": "restart_process", "script": str(SCORE_PUBLISHER_SCRIPT), "priority": "medium"},
    "DASHBOARD_STALE": {"action": "regenerate_dashboard", "priority": "low"},
    "LEGACY_DIRS_FOUND": {"action": "cleanup_legacy", "priority": "low"},
    "DUPLICATE_GENERATORS": {"action": "kill_duplicates", "priority": "medium"},
    "HARDCODED_API_KEYS": {"action": "flag_for_review", "priority": "high"},
    "SIMULATOR_LOG_ERRORS": {"action": "review_simulator_logs", "priority": "medium"},
    "META_VALIDATION_FAIL": {"action": "flag_bad_strategies", "priority": "medium"},
    "REPLENISHMENT_PENDING": {"action": "process_replenishment", "priority": "medium"},
    "ELIMINATIONS_DETECTED": {"action": "log_eliminations", "priority": "info"},
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def now_ts() -> float:
    return time.time()


def file_age(path: Path) -> Optional[float]:
    """Return age in seconds, or None if file missing."""
    try:
        return now_ts() - path.stat().st_mtime
    except (FileNotFoundError, OSError):
        return None


def load_json(path: Path) -> Any:
    """Load JSON file, return None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def save_json(path: Path, data: Any) -> None:
    """Atomically write JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


def is_process_running(script_name: str) -> bool:
    """Check if a Python process with the given script name is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", script_name],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Fallback: use ps
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True, text=True, timeout=5
            )
            return script_name in result.stdout
        except Exception:
            return False


def start_process(script_path: Path) -> bool:
    """Start a Python script in the background."""
    try:
        subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(script_path.parent),
            start_new_session=True,
        )
        return True
    except Exception:
        return False


def tail_file(path: Path, lines: int = 50) -> List[str]:
    """Read last N lines of a file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            return all_lines[-lines:]
    except (FileNotFoundError, OSError):
        return []


# ---------------------------------------------------------------------------
# A: EA Bridge Patrol
# ---------------------------------------------------------------------------
def patrol_ea_bridge(issues: List[Dict], actions: List[Dict]) -> Dict[str, Any]:
    """Check ea_bridge.py — process, EA connection, CSV freshness, price."""
    status: Dict[str, Any] = {"name": "ea_bridge", "running": False, "details": {}}

    # 1. Process check (WSL: pgrep can't see bg processes, so also check data freshness)
    running = is_process_running("ea_bridge")
    status["running"] = running
    
    # Check CSV freshness first — if data is flowing, bridge is effectively running
    csv_candidates = list(LIVE_DATA.glob("*.csv"))
    data_is_fresh = False
    if csv_candidates:
        freshest_age = min(file_age(p) or float("inf") for p in csv_candidates)
        data_is_fresh = freshest_age < 120  # data updated within 2 min = bridge running
    
    if not running and not EA_EXPECTED_OFFLINE:
        if data_is_fresh:
            # Data is flowing — bridge is running but WSL pgrep can't see it
            status["running"] = True
            status["details"]["process"] = "RUNNING_UNVISIBLE (data fresh)"
        else:
            issue = {
                "id": "EA_BRIDGE_DOWN",
                "severity": SEV_CRITICAL,
                "message": "ea_bridge.py process is not running",
                "detected_at": now_iso(),
            }
            issues.append(issue)
            actions.append({"issue_id": "EA_BRIDGE_DOWN", "action": "auto_fix_restart", "target": "ea_bridge.py"})
            status["details"]["process"] = "DOWN"
    elif not running and EA_EXPECTED_OFFLINE:
        status["details"]["process"] = "EXPECTED_OFFLINE"
    else:
        status["details"]["process"] = "RUNNING"

    # 2. CSV freshness
    csv_candidates = list(LIVE_DATA.glob("*.csv"))
    if csv_candidates:
        freshest = min(csv_candidates, key=lambda p: file_age(p) or float("inf"))
        age = file_age(freshest)
        status["details"]["latest_csv"] = str(freshest.name)
        status["details"]["csv_age_sec"] = age
        if age is not None and age > CSV_FRESHNESS_THRESHOLD:
            issue = {
                "id": "EA_BRIDGE_STALE_CSV",
                "severity": SEV_HIGH,
                "message": f"EA CSV is stale ({age:.0f}s old, threshold {CSV_FRESHNESS_THRESHOLD}s)",
                "detected_at": now_iso(),
            }
            issues.append(issue)
    else:
        status["details"]["latest_csv"] = None
        issue = {
            "id": "EA_BRIDGE_STALE_CSV",
            "severity": SEV_HIGH,
            "message": "No CSV files found in live_data/",
            "detected_at": now_iso(),
        }
        issues.append(issue)

    # 3. EA connection check (look for connection status in logs or ea_bridge log)
    ea_log_candidates = list(LOGS.glob("ea_bridge*")) + list(CONTROL.glob("ea_bridge*.log"))
    if ea_log_candidates:
        ea_log = ea_log_candidates[0]
        last_lines = tail_file(ea_log, 20)
        status["details"]["log_tail"] = "".join(last_lines[-5:])
        # Check for common error patterns
        log_text = "".join(last_lines)
        if "ERROR" in log_text or "disconnect" in log_text.lower():
            status["details"]["ea_connection"] = "ERROR"
        else:
            status["details"]["ea_connection"] = "OK"
    else:
        status["details"]["ea_connection"] = "UNKNOWN"

    # 4. Price check — look for latest price data in live_data
    price_files = list(LIVE_DATA.glob("price*")) + list(LIVE_DATA.glob("*tick*"))
    if price_files:
        latest_price = min(price_files, key=lambda p: file_age(p) or float("inf"))
        status["details"]["price_file"] = str(latest_price.name)
        try:
            price_data = load_json(latest_price)
            if isinstance(price_data, dict):
                status["details"]["last_price"] = price_data.get("bid") or price_data.get("price")
        except Exception:
            pass
    else:
        status["details"]["price_file"] = None

    return status


# ---------------------------------------------------------------------------
# B: Arena Simulator Patrol
# ---------------------------------------------------------------------------
def patrol_simulator(issues: List[Dict], actions: List[Dict]) -> Dict[str, Any]:
    """Check arena_simulator.py — process, strategy counts, log errors, META."""
    status: Dict[str, Any] = {"name": "arena_simulator", "running": False, "details": {}}

    # 1. Process check
    running = is_process_running("arena_simulator")
    status["running"] = running
    if not running:
        issue = {
            "id": "SIMULATOR_DOWN",
            "severity": SEV_HIGH,
            "message": "arena_simulator.py process is not running",
            "detected_at": now_iso(),
        }
        issues.append(issue)
        status["details"]["process"] = "DOWN"
    else:
        status["details"]["process"] = "RUNNING"

    # 2. Strategy counts per module
    strategy_counts: Dict[str, int] = {}
    total_count = 0
    for module in MODULES:
        module_dir = CONTESTANTS / module
        if module_dir.is_dir():
            strategies = list(module_dir.glob("**/*.py")) + list(module_dir.glob("**/*.json"))
            # Count strategy files (exclude __init__, __pycache__)
            strat_files = [s for s in strategies if "__init__" not in s.name and "__pycache__" not in str(s)]
            count = len(strat_files)
            strategy_counts[module] = count
            total_count += count

            if count < TARGET_PER_MODULE:
                need = TARGET_PER_MODULE - count
                issue = {
                    "id": "STRATEGY_COUNT_LOW",
                    "severity": SEV_MEDIUM if count < 50 else SEV_LOW,
                    "message": f"Module '{module}' has {count}/{TARGET_PER_MODULE} strategies (need {need})",
                    "module": module,
                    "detected_at": now_iso(),
                }
                issues.append(issue)
        else:
            strategy_counts[module] = 0
            issue = {
                "id": "STRATEGY_COUNT_LOW",
                "severity": SEV_HIGH,
                "message": f"Module '{module}' directory missing",
                "module": module,
                "detected_at": now_iso(),
            }
            issues.append(issue)

    status["details"]["strategy_counts"] = strategy_counts
    status["details"]["total_strategies"] = total_count
    status["details"]["target_total"] = TARGET_PER_MODULE * len(MODULES)

    # 3. Simulator log errors
    sim_log_candidates = list(LOGS.glob("simulator*")) + list(LOGS.glob("arena_sim*"))
    if not sim_log_candidates:
        sim_log_candidates = list(CONTROL.glob("*.log"))
    if sim_log_candidates:
        log_text = ""
        for lf in sim_log_candidates:
            log_text += "".join(tail_file(lf, 100))
        error_lines = [l for l in log_text.splitlines() if "ERROR" in l or "CRITICAL" in l]
        if error_lines:
            issue = {
                "id": "SIMULATOR_LOG_ERRORS",
                "severity": SEV_MEDIUM,
                "message": f"Found {len(error_lines)} error lines in simulator logs",
                "detected_at": now_iso(),
            }
            issues.append(issue)
            status["details"]["log_errors"] = len(error_lines)
            status["details"]["last_error"] = error_lines[-1][:200]
        else:
            status["details"]["log_errors"] = 0
    else:
        status["details"]["log_errors"] = 0

    # 4. Strategy META validation — spot-check a few strategies
    meta_failures = 0
    for module in MODULES:
        module_dir = CONTESTANTS / module
        if not module_dir.is_dir():
            continue
        # Look for strategy metadata files
        meta_files = list(module_dir.glob("**/*meta*.json")) + list(module_dir.glob("**/*config*.json"))
        for mf in meta_files[:5]:  # sample first 5
            data = load_json(mf)
            if data is None:
                meta_failures += 1
                continue
            # Basic validation: must have name, strategy_type or similar
            if isinstance(data, dict):
                has_name = bool(data.get("name") or data.get("strategy_name"))
                has_type = bool(data.get("strategy_type") or data.get("type"))
                if not has_name or not has_type:
                    meta_failures += 1
    if meta_failures > 0:
        issue = {
            "id": "META_VALIDATION_FAIL",
            "severity": SEV_MEDIUM,
            "message": f"{meta_failures} strategy META files failed validation",
            "detected_at": now_iso(),
        }
        issues.append(issue)
    status["details"]["meta_failures"] = meta_failures

    return status


# ---------------------------------------------------------------------------
# C: Signal Engine Patrol
# ---------------------------------------------------------------------------
def patrol_signal_engine(issues: List[Dict], actions: List[Dict]) -> Dict[str, Any]:
    """Check signal_engine.py — process, proposed signal freshness."""
    status: Dict[str, Any] = {"name": "signal_engine", "running": False, "details": {}}

    running = is_process_running("signal_engine")
    status["running"] = running
    if not running:
        issue = {
            "id": "SIGNAL_ENGINE_DOWN",
            "severity": SEV_HIGH,
            "message": "signal_engine.py process is not running",
            "detected_at": now_iso(),
        }
        issues.append(issue)
        status["details"]["process"] = "DOWN"
    else:
        status["details"]["process"] = "RUNNING"

    # Check signal freshness
    signal_files = []
    if SIGNALS.is_dir():
        signal_files = list(SIGNALS.glob("*.json")) + list(SIGNALS.glob("*.csv"))
    if signal_files:
        freshest = min(signal_files, key=lambda p: file_age(p) or float("inf"))
        age = file_age(freshest)
        status["details"]["latest_signal"] = str(freshest.name)
        status["details"]["signal_age_sec"] = age
        if age is not None and age > SIGNAL_FRESHNESS_THRESHOLD:
            issue = {
                "id": "SIGNALS_STALE",
                "severity": SEV_MEDIUM,
                "message": f"Latest signal is {age:.0f}s old (threshold {SIGNAL_FRESHNESS_THRESHOLD}s)",
                "detected_at": now_iso(),
            }
            issues.append(issue)
    else:
        status["details"]["latest_signal"] = None
        status["details"]["signal_count"] = 0

    # Count proposed signals
    proposed = [f for f in signal_files if "proposed" in f.name.lower() or "pending" in f.name.lower()]
    status["details"]["proposed_count"] = len(proposed)

    return status


# ---------------------------------------------------------------------------
# D: Referee Engine Patrol
# ---------------------------------------------------------------------------
def patrol_referee(issues: List[Dict], actions: List[Dict]) -> Dict[str, Any]:
    """Check referee_engine.py — process, eliminations, replenishment."""
    status: Dict[str, Any] = {"name": "referee_engine", "running": False, "details": {}}

    running = is_process_running("referee_engine")
    status["running"] = running
    if not running:
        issue = {
            "id": "REFEREE_DOWN",
            "severity": SEV_HIGH,
            "message": "referee_engine.py process is not running",
            "detected_at": now_iso(),
        }
        issues.append(issue)
        status["details"]["process"] = "DOWN"
    else:
        status["details"]["process"] = "RUNNING"

    # Check eliminations (look in live_data)
    elim_files = list(LIVE_DATA.glob("*eliminat*")) + list(LIVE_DATA.glob("*removed*"))
    elim_count = 0
    if elim_files:
        latest_elim = min(elim_files, key=lambda p: file_age(p) or float("inf"))
        elim_data = load_json(latest_elim)
        if isinstance(elim_data, list):
            elim_count = len(elim_data)
        elif isinstance(elim_data, dict):
            elim_count = elim_data.get("count", len(elim_data.get("eliminated", [])))
    status["details"]["eliminations"] = elim_count
    if elim_count > 0:
        issue = {
            "id": "ELIMINATIONS_DETECTED",
            "severity": SEV_INFO,
            "message": f"{elim_count} eliminations recorded",
            "detected_at": now_iso(),
        }
        issues.append(issue)

    # Check replenishment requests
    replenish_data = load_json(REPLENISH_FILE)
    pending_requests: Dict[str, Any] = {}
    if isinstance(replenish_data, dict):
        modules_req = replenish_data.get("modules", {})
        for mod_name, req_info in modules_req.items():
            if isinstance(req_info, dict) and req_info.get("status") in ("pending", "requested"):
                pending_requests[mod_name] = req_info
    if pending_requests:
        issue = {
            "id": "REPLENISHMENT_PENDING",
            "severity": SEV_MEDIUM,
            "message": f"{len(pending_requests)} modules have pending replenishment requests",
            "modules": list(pending_requests.keys()),
            "detected_at": now_iso(),
        }
        issues.append(issue)
    status["details"]["pending_replenishments"] = len(pending_requests)
    status["details"]["replenishment_modules"] = list(pending_requests.keys())

    return status


# ---------------------------------------------------------------------------
# E: Score Publisher Patrol
# ---------------------------------------------------------------------------
def patrol_score_publisher(issues: List[Dict], actions: List[Dict]) -> Dict[str, Any]:
    """Check score_publisher.py — process, leaderboard freshness."""
    status: Dict[str, Any] = {"name": "score_publisher", "running": False, "details": {}}

    running = is_process_running("score_publisher")
    status["running"] = running
    if not running:
        issue = {
            "id": "SCORE_PUBLISHER_DOWN",
            "severity": SEV_HIGH,
            "message": "score_publisher.py process is not running",
            "detected_at": now_iso(),
        }
        issues.append(issue)
        actions.append({"issue_id": "SCORE_PUBLISHER_DOWN", "action": "auto_fix_restart", "target": "score_publisher.py"})
        status["details"]["process"] = "DOWN"
    else:
        status["details"]["process"] = "RUNNING"

    # Leaderboard freshness
    lb_files = []
    if LEADERBOARD.is_dir():
        lb_files = list(LEADERBOARD.glob("*.json")) + list(LEADERBOARD.glob("*.csv"))
    if lb_files:
        freshest = min(lb_files, key=lambda p: file_age(p) or float("inf"))
        age = file_age(freshest)
        status["details"]["latest_leaderboard"] = str(freshest.name)
        status["details"]["leaderboard_age_sec"] = age
        if age is not None and age > LEADERBOARD_FRESHNESS_THRESHOLD:
            issue = {
                "id": "LEADERBOARD_STALE",
                "severity": SEV_MEDIUM,
                "message": f"Leaderboard is stale ({age:.0f}s old, threshold {LEADERBOARD_FRESHNESS_THRESHOLD}s)",
                "detected_at": now_iso(),
            }
            issues.append(issue)
    else:
        status["details"]["latest_leaderboard"] = None

    return status


# ---------------------------------------------------------------------------
# F: Dashboard Patrol
# ---------------------------------------------------------------------------
def patrol_dashboard(issues: List[Dict], actions: List[Dict]) -> Dict[str, Any]:
    """Check dashboard_data.json freshness."""
    status: Dict[str, Any] = {"name": "dashboard", "details": {}}

    age = file_age(DASHBOARD_DATA_FILE)
    if age is None:
        status["details"]["data_file"] = "MISSING"
        issue = {
            "id": "DASHBOARD_STALE",
            "severity": SEV_LOW,
            "message": "dashboard_data.json not found",
            "detected_at": now_iso(),
        }
        issues.append(issue)
    else:
        status["details"]["data_file"] = "PRESENT"
        status["details"]["age_sec"] = age
        if age > DASHBOARD_FRESHNESS_THRESHOLD:
            issue = {
                "id": "DASHBOARD_STALE",
                "severity": SEV_LOW,
                "message": f"Dashboard data is stale ({age:.0f}s old)",
                "detected_at": now_iso(),
            }
            issues.append(issue)

    # Validate dashboard data contents
    dash_data = load_json(DASHBOARD_DATA_FILE)
    if isinstance(dash_data, dict):
        status["details"]["has_leaderboard"] = "leaderboard" in dash_data
        status["details"]["has_signals"] = "signals" in dash_data
        status["details"]["has_market"] = "market" in dash_data
    else:
        status["details"]["has_leaderboard"] = False
        status["details"]["has_signals"] = False
        status["details"]["has_market"] = False

    return status


# ---------------------------------------------------------------------------
# System-level Patrol
# ---------------------------------------------------------------------------
def patrol_system(issues: List[Dict], actions: List[Dict]) -> Dict[str, Any]:
    """Check for legacy dirs, duplicate generators, hardcoded API keys."""
    status: Dict[str, Any] = {"name": "system", "details": {}}

    # 1. Legacy directories
    legacy_patterns = ["strategies_old", "backup_*", "old_*", "archive", "_backup", "tmp_*"]
    legacy_found: List[str] = []
    for pattern in legacy_patterns:
        for d in ARENA_ROOT.glob(pattern):
            if d.is_dir():
                legacy_found.append(str(d.name))
    if legacy_found:
        issue = {
            "id": "LEGACY_DIRS_FOUND",
            "severity": SEV_LOW,
            "message": f"Legacy directories found: {', '.join(legacy_found)}",
            "detected_at": now_iso(),
        }
        issues.append(issue)
    status["details"]["legacy_dirs"] = legacy_found

    # 2. Duplicate generator processes
    gen_processes = []
    try:
        result = subprocess.run(
            ["pgrep", "-af", "generate"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    gen_processes.append({"pid": parts[0], "cmd": parts[1]})
    except Exception:
        pass

    if len(gen_processes) > 2:  # allow 1-2 generators
        issue = {
            "id": "DUPLICATE_GENERATORS",
            "severity": SEV_MEDIUM,
            "message": f"{len(gen_processes)} generator processes running (possible duplicates)",
            "pids": [p["pid"] for p in gen_processes],
            "detected_at": now_iso(),
        }
        issues.append(issue)
    status["details"]["generator_processes"] = len(gen_processes)

    # 3. Hardcoded API keys check
    api_key_pattern = re.compile(
        r'(?:api[_-]?key|apikey|secret|token|password)\s*[=:]\s*["\']([A-Za-z0-9_\-]{20,})["\']',
        re.IGNORECASE,
    )
    key_violations: List[str] = []
    search_dirs = [CONTROL, ARENA_ROOT / "config"]
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for py_file in search_dir.glob("**/*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                if api_key_pattern.search(content):
                    key_violations.append(str(py_file.name))
            except OSError:
                continue
        for json_file in search_dir.glob("**/*.json"):
            try:
                content = json_file.read_text(encoding="utf-8", errors="replace")
                if api_key_pattern.search(content):
                    key_violations.append(str(json_file.name))
            except OSError:
                continue

    if key_violations:
        issue = {
            "id": "HARDCODED_API_KEYS",
            "severity": SEV_HIGH,
            "message": f"Possible hardcoded API keys in: {', '.join(key_violations)}",
            "files": key_violations,
            "detected_at": now_iso(),
        }
        issues.append(issue)
    status["details"]["api_key_violations"] = key_violations

    return status


# ---------------------------------------------------------------------------
# Decision Engine
# ---------------------------------------------------------------------------
def compute_health_score(issues: List[Dict]) -> int:
    """Compute health score 0-100 based on issues."""
    score = 100
    deductions = {
        SEV_CRITICAL: 25,
        SEV_HIGH: 15,
        SEV_MEDIUM: 5,   # SEV_MEDIUM used for MEDIUM
        SEV_LOW: 2,
        SEV_INFO: 0,
    }
    for issue in issues:
        sev = issue.get("severity", SEV_INFO)
        score -= deductions.get(sev, 0)
    return max(0, score)


def determine_status(health_score: int, issues: List[Dict]) -> str:
    """Determine overall status from health score."""
    has_critical = any(i.get("severity") == SEV_CRITICAL for i in issues)
    if has_critical:
        return "CRITICAL"
    if health_score >= 80:
        return "HEALTHY"
    if health_score >= 60:
        return "DEGRADED"
    if health_score >= 40:
        return "UNHEALTHY"
    return "CRITICAL"


def get_max_severity(issues: List[Dict]) -> str:
    """Return the highest severity from all issues."""
    order = [SEV_CRITICAL, SEV_HIGH, SEV_MEDIUM, SEV_LOW, SEV_INFO]
    for sev in order:
        if any(i.get("severity") == sev for i in issues):
            return sev
    return SEV_INFO


# ---------------------------------------------------------------------------
# Auto-Fix Engine
# ---------------------------------------------------------------------------
def auto_fix_issues(issues: List[Dict], actions: List[Dict]) -> List[Dict]:
    """Auto-fix simple issues (restart downed processes)."""
    fixable_ids = {"EA_BRIDGE_DOWN", "SCORE_PUBLISHER_DOWN"}
    fixes_applied: List[Dict] = []

    for issue in issues:
        issue_id = issue.get("id")
        if issue_id not in fixable_ids:
            continue

        # Determine script to restart
        script_map = {
            "EA_BRIDGE_DOWN": EA_BRIDGE_SCRIPT,
            "SCORE_PUBLISHER_DOWN": SCORE_PUBLISHER_SCRIPT,
        }
        script = script_map.get(issue_id)
        if script and script.exists():
            success = start_process(script)
            fix_record = {
                "issue_id": issue_id,
                "action": "restart",
                "target": str(script.name),
                "success": success,
                "timestamp": now_iso(),
            }
            fixes_applied.append(fix_record)
            if success:
                issue["auto_fixed"] = True
                actions.append({
                    "issue_id": issue_id,
                    "action": "auto_fix_restart",
                    "target": str(script.name),
                    "result": "success",
                    "timestamp": now_iso(),
                })
            else:
                actions.append({
                    "issue_id": issue_id,
                    "action": "auto_fix_restart",
                    "target": str(script.name),
                    "result": "failed",
                    "timestamp": now_iso(),
                })

    return fixes_applied


# ---------------------------------------------------------------------------
# Dispatcher — write tasks for Worker Agent
# ---------------------------------------------------------------------------
def build_task_queue(issues: List[Dict], actions: List[Dict]) -> List[Dict]:
    """Build task queue from unresolved issues using ISSUE_TO_TASK mapping."""
    tasks: List[Dict] = []
    for issue in issues:
        if issue.get("auto_fixed"):
            continue
        issue_id = issue.get("id")
        task_template = ISSUE_TO_TASK.get(issue_id)
        if not task_template:
            continue
        task = {
            "task_id": f"task_{issue_id}_{int(now_ts())}",
            "issue_id": issue_id,
            "action": task_template["action"],
            "priority": task_template.get("priority", "medium"),
            "details": {
                "message": issue.get("message", ""),
                "severity": issue.get("severity", SEV_INFO),
            },
            "created_at": now_iso(),
            "status": "pending",
        }
        # Copy extra fields from template
        for key in ("script", "module"):
            if key in task_template:
                task["details"][key] = task_template[key]
        if "module" in issue:
            task["details"]["module"] = issue["module"]
        tasks.append(task)
    return tasks


def dispatch_tasks(tasks: List[Dict]) -> Optional[Dict[str, Any]]:
    """Write tasks to queue and optionally invoke worker_agent.py."""
    if not tasks:
        return None

    # Write task queue
    task_queue = {
        "tasks": tasks,
        "created_at": now_iso(),
        "count": len(tasks),
    }
    save_json(TASK_QUEUE_FILE, task_queue)

    # Try to invoke worker agent
    worker_result = None
    if WORKER_SCRIPT.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(WORKER_SCRIPT)],
                capture_output=True, text=True, timeout=120,
                cwd=str(CONTROL),
            )
            worker_result = {
                "exit_code": result.returncode,
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "stderr": result.stderr[-1000:] if result.stderr else "",
            }
        except subprocess.TimeoutExpired:
            worker_result = {"exit_code": -1, "error": "timeout"}
        except Exception as e:
            worker_result = {"exit_code": -1, "error": str(e)}

    return {"task_queue": task_queue, "worker_result": worker_result}


# ---------------------------------------------------------------------------
# Heartbeat Writer
# ---------------------------------------------------------------------------
def write_heartbeat(
    health_score: int,
    status: str,
    issues: List[Dict],
    services: List[Dict[str, Any]],
    patrol_duration: float,
    current_state: str = "IDLE",
) -> None:
    """Write plan_heartbeat.json."""
    heartbeat = {
        "timestamp": now_iso(),
        "current_state": current_state,
        "health_score": health_score,
        "status": status,
        "patrol_duration_sec": round(patrol_duration, 2),
        "services": services,
        "issue_count": len(issues),
        "issues_summary": [
            {"id": i.get("id"), "severity": i.get("severity"), "message": i.get("message", "")[:100]}
            for i in issues
        ],
        "modules": {
            mod: {"target": TARGET_PER_MODULE}
            for mod in MODULES
        },
    }
    save_json(HEARTBEAT_FILE, heartbeat)


# ---------------------------------------------------------------------------
# Command Checker — read plan_command.json for Hermes commands
# ---------------------------------------------------------------------------
def check_command_channel() -> Optional[Dict[str, Any]]:
    """Read plan_command.json and process Hermes commands."""
    if not COMMAND_FILE.exists():
        return None

    cmd_data = load_json(COMMAND_FILE)
    if not cmd_data or not isinstance(cmd_data, dict):
        return None

    command = cmd_data.get("command", "").strip().lower()
    if not command:
        return None

    response: Dict[str, Any] = {
        "command": command,
        "received_at": cmd_data.get("timestamp", now_iso()),
        "processed_at": now_iso(),
    }

    if command == "status":
        response["action"] = "report_status"
        response["status"] = "acknowledged"
        # Read current heartbeat
        hb = load_json(HEARTBEAT_FILE)
        if hb:
            response["current_health"] = hb.get("health_score")
            response["current_status"] = hb.get("status")

    elif command == "restart":
        response["action"] = "restart_all"
        response["status"] = "acknowledged"
        # Restart key services
        for script in [EA_BRIDGE_SCRIPT, SIMULATOR_SCRIPT, SIGNAL_ENGINE_SCRIPT, REFEREE_SCRIPT, SCORE_PUBLISHER_SCRIPT]:
            if script.exists():
                start_process(script)

    elif command == "pause":
        response["action"] = "pause_patrol"
        response["status"] = "acknowledged"
        # Write a pause flag
        pause_flag = CONTROL / ".plan_paused"
        pause_flag.touch()

    elif command == "resume":
        response["action"] = "resume_patrol"
        response["status"] = "acknowledged"
        pause_flag = CONTROL / ".plan_paused"
        if pause_flag.exists():
            pause_flag.unlink()

    else:
        response["action"] = "unknown"
        response["status"] = "ignored"
        response["message"] = f"Unknown command: {command}"

    # Write response back
    cmd_response_file = CONTROL / "plan_command_response.json"
    save_json(cmd_response_file, response)

    # Clear the command file after processing
    try:
        COMMAND_FILE.unlink()
    except OSError:
        pass

    return response


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------
def generate_report(
    health_score: int,
    status: str,
    issues: List[Dict],
    actions: List[Dict],
    services: List[Dict[str, Any]],
    fixes_applied: List[Dict],
    dispatch_info: Optional[Dict],
    command_response: Optional[Dict],
    patrol_duration: float,
) -> Dict[str, Any]:
    """Generate plan_agent_report.json."""
    max_severity = get_max_severity(issues)

    # Separate escalations (CRITICAL/HIGH issues that weren't auto-fixed)
    escalations = [
        i for i in issues
        if i.get("severity") in (SEV_CRITICAL, SEV_HIGH) and not i.get("auto_fixed")
    ]

    report = {
        "report_type": "plan_agent_patrol",
        "generated_at": now_iso(),
        "patrol_duration_sec": round(patrol_duration, 2),
        "summary": {
            "health_score": health_score,
            "status": status,
            "max_severity": max_severity,
            "total_issues": len(issues),
            "critical_issues": sum(1 for i in issues if i.get("severity") == SEV_CRITICAL),
            "high_issues": sum(1 for i in issues if i.get("severity") == SEV_HIGH),
            "medium_issues": sum(1 for i in issues if i.get("severity") in ("MEDIUM", SEV_MEDIUM)),
            "low_issues": sum(1 for i in issues if i.get("severity") == SEV_LOW),
            "auto_fixes_applied": len(fixes_applied),
            "tasks_dispatched": len(dispatch_info.get("task_queue", {}).get("tasks", [])) if dispatch_info else 0,
        },
        "services": services,
        "issues": issues,
        "actions": actions,
        "fixes_applied": fixes_applied,
        "escalations": escalations,
        "command_response": command_response,
    }

    save_json(REPORT_FILE, report)
    return report


# ---------------------------------------------------------------------------
# Main Patrol Orchestration
# ---------------------------------------------------------------------------
def run_patrol(do_fix: bool = False, do_dispatch: bool = False) -> Dict[str, Any]:
    """Run a full patrol cycle A→B→C→D→E→F + system checks."""
    global _state_log
    _state_log = []  # reset for each patrol
    patrol_start = time.time()
    issues: List[Dict] = []
    actions: List[Dict] = []

    _set_state(PlanState.INIT)
    print(f"[{now_iso()}] PLAN Agent patrol starting...")
    print(f"  ARENA_ROOT: {ARENA_ROOT}")

    # Check if paused
    pause_flag = CONTROL / ".plan_paused"
    if pause_flag.exists():
        print("  [PAUSED] Patrol skipped — .plan_paused flag found.")
        return {
            "status": "PAUSED",
            "health_score": 0,
            "issues": [],
            "services": [],
            "duration": 0,
        }

    _set_state(PlanState.HEALTH_CHECK)
    # --- Patrol A: EA Bridge ---
    print("  [A] Checking ea_bridge...")
    svc_a = patrol_ea_bridge(issues, actions)

    # --- Patrol B: Simulator ---
    print("  [B] Checking arena_simulator...")
    svc_b = patrol_simulator(issues, actions)

    # --- Patrol C: Signal Engine ---
    print("  [C] Checking signal_engine...")
    svc_c = patrol_signal_engine(issues, actions)

    # --- Patrol D: Referee ---
    print("  [D] Checking referee_engine...")
    svc_d = patrol_referee(issues, actions)

    # --- Patrol E: Score Publisher ---
    print("  [E] Checking score_publisher...")
    svc_e = patrol_score_publisher(issues, actions)

    # --- Patrol F: Dashboard ---
    print("  [F] Checking dashboard...")
    svc_f = patrol_dashboard(issues, actions)

    # --- System checks ---
    print("  [S] Running system checks...")
    svc_sys = patrol_system(issues, actions)

    services = [svc_a, svc_b, svc_c, svc_d, svc_e, svc_f, svc_sys]

    # --- Health scoring ---
    health_score = compute_health_score(issues)
    overall_status = determine_status(health_score, issues)

    _set_state(PlanState.DIAGNOSE)
    print(f"  Health Score: {health_score}/100  Status: {overall_status}")
    print(f"  Issues found: {len(issues)}")

    # --- Auto-fix ---
    fixes_applied: List[Dict] = []
    if do_fix and issues:
        _set_state(PlanState.AUTO_REPAIR)
        print("  [FIX] Applying auto-fixes...")
        fixes_applied = auto_fix_issues(issues, actions)
        print(f"  [FIX] Applied {len(fixes_applied)} fix(es).")

    # --- Dispatch ---
    dispatch_info: Optional[Dict] = None
    if do_dispatch and issues:
        tasks = build_task_queue(issues, actions)
        if tasks:
            _set_state(PlanState.DISPATCH)
            print(f"  [DISPATCH] Dispatching {len(tasks)} task(s) to Worker Agent...")
            dispatch_info = dispatch_tasks(tasks)
            if dispatch_info and dispatch_info.get("worker_result"):
                wr = dispatch_info["worker_result"]
                print(f"  [DISPATCH] Worker exit code: {wr.get('exit_code', 'N/A')}")

    # --- Verify fixes ---
    if fixes_applied:
        _set_state(PlanState.VERIFY)
        print("  [VERIFY] Checking if fixes took effect...")
        # Re-check processes that were restarted
        for fix in fixes_applied:
            target = fix.get("target", "")
            if fix.get("success"):
                still_running = is_process_running(target.replace(".py", ""))
                print(f"    {target}: {'RUNNING' if still_running else 'STILL DOWN'}")

    # --- Command channel ---
    print("  [CMD] Checking command channel...")
    command_response = check_command_channel()
    if command_response:
        print(f"  [CMD] Processed command: {command_response.get('command')}")

    # --- Report ---
    _set_state(PlanState.REPORT)
    # --- Write heartbeat ---
    patrol_duration = time.time() - patrol_start
    print("  [HB] Writing heartbeat...")
    current_state_val = PlanState.REPORT.value
    write_heartbeat(health_score, overall_status, issues, services, patrol_duration, current_state=current_state_val)

    # --- Final state: ESCALATE if critical unfixed issues, else IDLE ---
    has_unfixed_critical = any(
        i.get("severity") in (SEV_CRITICAL, SEV_HIGH) and not i.get("auto_fixed")
        for i in issues
    )
    if has_unfixed_critical:
        _set_state(PlanState.ESCALATE)
        # Update heartbeat with escalate state
        write_heartbeat(health_score, overall_status, issues, services, patrol_duration, current_state=PlanState.ESCALATE.value)
    else:
        _set_state(PlanState.IDLE)
        write_heartbeat(health_score, overall_status, issues, services, patrol_duration, current_state=PlanState.IDLE.value)

    print(f"  Patrol complete in {patrol_duration:.2f}s")

    return {
        "status": overall_status,
        "health_score": health_score,
        "issues": issues,
        "actions": actions,
        "services": services,
        "fixes_applied": fixes_applied,
        "dispatch_info": dispatch_info,
        "command_response": command_response,
        "duration": patrol_duration,
    }


def run_report_only() -> Dict[str, Any]:
    """Run patrol and generate report only (no fixes, no dispatch)."""
    result = run_patrol(do_fix=False, do_dispatch=False)
    report = generate_report(
        health_score=result["health_score"],
        status=result["status"],
        issues=result["issues"],
        actions=result.get("actions", []),
        services=result["services"],
        fixes_applied=[],
        dispatch_info=None,
        command_response=result.get("command_response"),
        patrol_duration=result["duration"],
    )
    print(f"\n  Report written to: {REPORT_FILE}")
    return report


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="PLAN Agent — 百大交易競技場 Arena Manager"
    )
    parser.add_argument("--fix", action="store_true", help="Auto-fix simple issues (restart downed processes)")
    parser.add_argument("--dispatch", action="store_true", help="Dispatch tasks to Worker Agent")
    parser.add_argument("--report-only", action="store_true", help="Generate report only, no fixes or dispatch")
    args = parser.parse_args()

    # Ensure key directories exist
    for d in [CONTROL, LIVE_DATA, SIGNALS, LEADERBOARD, DASHBOARD, LOGS]:
        d.mkdir(parents=True, exist_ok=True)

    if args.report_only:
        report = run_report_only()
        health = report.get("summary", {}).get("health_score", 0)
        max_sev = report.get("summary", {}).get("max_severity", SEV_INFO)
        if max_sev == SEV_CRITICAL:
            return 2
        elif max_sev == SEV_HIGH or health < 60:
            return 1
        return 0

    result = run_patrol(do_fix=args.fix, do_dispatch=args.dispatch)

    # Always generate report
    report = generate_report(
        health_score=result["health_score"],
        status=result["status"],
        issues=result["issues"],
        actions=result.get("actions", []),
        services=result["services"],
        fixes_applied=result.get("fixes_applied", []),
        dispatch_info=result.get("dispatch_info"),
        command_response=result.get("command_response"),
        patrol_duration=result["duration"],
    )

    # Print summary
    print("\n" + "=" * 60)
    print(f"  PATROL SUMMARY")
    print(f"  Health Score: {result['health_score']}/100")
    print(f"  Status:       {result['status']}")
    print(f"  Issues:       {len(result['issues'])}")
    if result["issues"]:
        for i in result["issues"]:
            sev = i.get("severity", "?")
            msg = i.get("message", "")[:80]
            fixed = " [AUTO-FIXED]" if i.get("auto_fixed") else ""
            print(f"    [{sev}] {msg}{fixed}")
    if result.get("fixes_applied"):
        print(f"  Auto-fixes:   {len(result['fixes_applied'])}")
    print(f"  Report:       {REPORT_FILE}")
    print(f"  Heartbeat:    {HEARTBEAT_FILE}")
    print("=" * 60)

    # Exit code based on severity
    max_sev = get_max_severity(result["issues"])
    if max_sev == SEV_CRITICAL:
        return 2
    elif max_sev == SEV_HIGH or result["health_score"] < 60:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
