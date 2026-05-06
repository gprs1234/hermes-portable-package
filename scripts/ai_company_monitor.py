#!/usr/bin/env python3
"""
AI Company Monitor - watches board_bot.py and watchdog.py processes.
Checks project health, venv, .env, and outputs heartbeat JSON files.
Auto-restart with --fix flag.

Usage: python3 ai_company_monitor.py [--fix]
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────
HOME = Path.home()
PROJECT_DIR = HOME / "projects" / "ai_company"
VENV_DIR = PROJECT_DIR / ".venv"
ENV_FILE = HOME / "projects" / ".env"
BOARD_BOT_PY = PROJECT_DIR / "board_bot.py"
WATCHDOG_PY = PROJECT_DIR / "watchdog.py"

HEARTBEAT_DIR = HOME / ".hermes" / "plan_registry"
BOARD_HEARTBEAT = HEARTBEAT_DIR / "board_bot_heartbeat.json"
WATCHDOG_HEARTBEAT = HEARTBEAT_DIR / "watchdog_heartbeat.json"


def restart_cmd(script: str) -> str:
    """Kill all existing instances first, then start one. Prevents duplicates."""
    return (
        f"pkill -f 'python3.*{script}' 2>/dev/null; sleep 1; "
        f"cd {PROJECT_DIR} && "
        f"source {ENV_FILE} && "
        f".venv/bin/python3 {script}"
    )


def is_process_running(name_pattern: str) -> bool:
    """Check if any python3 process matching the name is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"python3.*{name_pattern}"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def check_venv():
    if VENV_DIR.exists():
        python_bin = VENV_DIR / "bin" / "python3"
        if python_bin.exists():
            return True, "venv present with python3"
        return True, "venv dir exists but no python3 binary"
    return False, ".venv missing"


def check_env():
    if not ENV_FILE.exists():
        return False, ".env file missing"
    content = ENV_FILE.read_text()
    has_key = any(
        line.strip() and "=" in line and not line.strip().startswith("#")
        for line in content.splitlines()
    )
    if has_key:
        return True, ".env exists with keys"
    return True, ".env exists but looks empty"


def check_project_dir():
    if not PROJECT_DIR.exists():
        return False, "project directory missing"
    missing = []
    if not BOARD_BOT_PY.exists():
        missing.append("board_bot.py")
    if not WATCHDOG_PY.exists():
        missing.append("watchdog.py")
    if missing:
        return False, f"missing: {', '.join(missing)}"
    return True, "project dir OK, scripts present"


def make_heartbeat(plan_id, name, health_score, issues, critical_issues,
                   services, auto_actions):
    if health_score >= 80:
        status, emoji = "HEALTHY", "\U0001f7e2"
    elif health_score >= 50:
        status, emoji = "ATTENTION", "\U0001f7e1"
    else:
        status, emoji = "CRITICAL", "\U0001f534"

    return {
        "plan_id": plan_id,
        "name": name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "health_score": health_score,
        "status": status,
        "status_emoji": emoji,
        "total_issues": len(issues),
        "critical_issues": critical_issues,
        "services": services,
        "auto_actions": auto_actions,
    }


def _preserve_heartbeat_metadata(path, data):
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        existing = {}
    for key in (
        "health_source",
        "external_verified",
        "trust_level",
        "confidence",
        "metadata_reviewed_by",
        "metadata_reviewed_at",
        "metadata_review_note",
    ):
        if key in existing and key not in data:
            data[key] = existing[key]
    return data

def write_heartbeat(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _preserve_heartbeat_metadata(path, data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description="AI Company Monitor")
    parser.add_argument("--fix", action="store_true",
                        help="Attempt auto-restart of down processes")
    args = parser.parse_args()

    HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)

    # ── shared checks ───────────────────────────────────────────────
    proj_ok, proj_msg = check_project_dir()
    venv_ok, venv_msg = check_venv()
    env_ok, env_msg = check_env()

    board_running = is_process_running("board_bot.py")
    watchdog_running = is_process_running("watchdog.py")

    auto_actions_bb = []
    auto_actions_wd = []

    # ── board bot ───────────────────────────────────────────────────
    bb_score = 100
    bb_issues = []
    bb_critical = []

    if not proj_ok:
        bb_score -= 40
        bb_issues.append(proj_msg)
        bb_critical.append(proj_msg)
    if not venv_ok:
        bb_score -= 30
        bb_issues.append(venv_msg)
        bb_critical.append(venv_msg)
    if not env_ok:
        bb_score -= 20
        bb_issues.append(env_msg)
        bb_critical.append(env_msg)
    if not board_running:
        bb_score -= 40
        bb_issues.append("board_bot.py not running")
        bb_critical.append("board_bot process DOWN")
        if args.fix and proj_ok and venv_ok:
            cmd = restart_cmd("board_bot.py")
            subprocess.Popen(cmd, shell=True, executable="/bin/bash")
            auto_actions_bb.append("auto-restart: " + cmd)

    bb_score = max(0, bb_score)

    bb_heartbeat = make_heartbeat(
        plan_id="board-bot",
        name="\u8463\u4e8b\u6703 Bot",
        health_score=bb_score,
        issues=bb_issues,
        critical_issues=bb_critical,
        services={"process": {"running": board_running}},
        auto_actions=auto_actions_bb,
    )
    write_heartbeat(BOARD_HEARTBEAT, bb_heartbeat)

    # ── watchdog (extra critical — sole observer of the company) ────
    wd_score = 100
    wd_issues = []
    wd_critical = []

    if not proj_ok:
        wd_score -= 40
        wd_issues.append(proj_msg)
        wd_critical.append(proj_msg)
    if not venv_ok:
        wd_score -= 30
        wd_issues.append(venv_msg)
        wd_critical.append(venv_msg)
    if not env_ok:
        wd_score -= 20
        wd_issues.append(env_msg)
        wd_critical.append(env_msg)
    if not watchdog_running:
        # extra critical penalty — watchdog is the sole observer
        wd_score -= 50
        wd_issues.append("watchdog.py not running")
        wd_critical.append("watchdog process DOWN - NO MONITORING ACTIVE")
        wd_critical.append(
            "Watchdog is the company's sole observer; its absence is critical"
        )
        if args.fix and proj_ok and venv_ok:
            cmd = restart_cmd("watchdog.py")
            subprocess.Popen(cmd, shell=True, executable="/bin/bash")
            auto_actions_wd.append("auto-restart: " + cmd)

    wd_score = max(0, wd_score)

    wd_heartbeat = make_heartbeat(
        plan_id="watchdog",
        name="AI Company Watchdog",
        health_score=wd_score,
        issues=wd_issues,
        critical_issues=wd_critical,
        services={"process": {"running": watchdog_running}},
        auto_actions=auto_actions_wd,
    )
    write_heartbeat(WATCHDOG_HEARTBEAT, wd_heartbeat)

    # ── terminal output ─────────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print("[{}] AI Company Monitor".format(ts))
    print("  Project dir : {} ({})".format("OK" if proj_ok else "FAIL", proj_msg))
    print("  Venv        : {} ({})".format("OK" if venv_ok else "FAIL", venv_msg))
    print("  .env        : {} ({})".format("OK" if env_ok else "FAIL", env_msg))
    print("  board_bot   : {} -> {} {} (score {})".format(
        "RUNNING" if board_running else "DOWN",
        bb_heartbeat["status_emoji"], bb_heartbeat["status"], bb_score))
    print("  watchdog    : {} -> {} {} (score {})".format(
        "RUNNING" if watchdog_running else "DOWN",
        wd_heartbeat["status_emoji"], wd_heartbeat["status"], wd_score))
    if not watchdog_running:
        print("  !! WATCHDOG DOWN - nobody is monitoring the company !!")
    if args.fix:
        if auto_actions_bb:
            print("  Board fix: {}".format(auto_actions_bb))
        if auto_actions_wd:
            print("  Watchdog fix: {}".format(auto_actions_wd))
    print("  Heartbeats: {}".format(BOARD_HEARTBEAT))
    print("              {}".format(WATCHDOG_HEARTBEAT))

    # exit code: 0 healthy, 1 attention, 2 critical
    worst = min(bb_score, wd_score)
    if worst < 50:
        sys.exit(2)
    elif worst < 80:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
