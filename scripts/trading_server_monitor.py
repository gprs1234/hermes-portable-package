#!/usr/bin/env python3
"""
Trading Server PLAN Monitor
Monitors server_file.py process, EA bridge status, and arena live data directory.
Reads EA data from ECMARKET ea_bridge (arena/signals + arena/live_data).
Supports auto-restart with --fix flag.
Outputs heartbeat JSON to ~/.hermes/plan_registry/trading_server_heartbeat.json

Usage:
  python3 trading_server_monitor.py               # full check + output
  python3 trading_server_monitor.py --fix          # full check + auto-restart if needed
  python3 trading_server_monitor.py --heartbeat-only  # just write heartbeat, print JSON
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# === Configuration ===
HOME = Path.home()
TRADING_SERVER_PY = HOME / "projects" / "trading" / "server_file.py"
TRADING_PROJECT_DIR = HOME / "projects" / "trading"
VENV_PYTHON = TRADING_PROJECT_DIR / ".venv" / "bin" / "python3"

# EA data: read from ECMARKET EA via arena's ea_bridge (NOT /mnt/c/trading/ea_data.json which is old TMGM data)
ARENA_ROOT = Path("/mnt/c/Users/User/Desktop/百大交易競技場/arena")
EA_BRIDGE_STATUS = ARENA_ROOT / "signals" / "ea_bridge_status.json"
EA_LIVE_DATA = ARENA_ROOT / "live_data" / "data_xauusd_M15.csv"

HEARTBEAT_PATH = HOME / ".hermes" / "plan_registry" / "trading_server_heartbeat.json"
COMMAND_PATH = HOME / ".hermes" / "plan_registry" / "trading_command.json"
RESPONSE_PATH = HOME / ".hermes" / "plan_registry" / "trading_response.json"

# Thresholds
STALE_SECONDS_WARNING = 300    # 5 minutes = ATTENTION
STALE_SECONDS_CRITICAL = 600   # 10 minutes = CRITICAL
PRICE_ZERO_THRESHOLD = 0.0     # price == 0.0 means EA disconnected


# === Checks ===

def check_server_process():
    """Check if server_file.py process is running."""
    result = {"running": False, "pid": None, "errors": []}
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "python3.*server_file\\.py"],
            capture_output=True, text=True
        )
        if proc.returncode == 0:
            pids = proc.stdout.strip().split("\n")
            result["running"] = True
            result["pid"] = int(pids[0]) if pids[0] else None
    except Exception as e:
        result["errors"].append("Process check failed: " + str(e))
    return result


def check_ea_data_json():
    """Check EA data from ECMARKET ea_bridge: bridge status JSON + live data CSV."""
    result = {
        "file_found": False,
        "file_path": None,
        "file_readable": False,
        "price": 0.0,
        "bid": 0.0,
        "ask": 0.0,
        "data_age_seconds": None,
        "last_modified": None,
        "connected": False,
        "errors": []
    }

    # --- 1) Check EA bridge status JSON ---
    bridge_ok = False
    bridge_age = None
    if EA_BRIDGE_STATUS.exists():
        result["file_found"] = True
        result["file_path"] = str(EA_BRIDGE_STATUS)
        try:
            with open(EA_BRIDGE_STATUS, "r", encoding="utf-8") as f:
                bridge_data = json.load(f)
            result["file_readable"] = True
            synced_at = bridge_data.get("synced_at")
            if synced_at:
                # Parse ISO timestamp (may be naive or have Z suffix)
                sync_dt = datetime.fromisoformat(synced_at.replace("Z", "+00:00"))
                # Ensure timezone-aware (assume local tz if naive, since ea_bridge writes local time)
                if sync_dt.tzinfo is None:
                    sync_dt = sync_dt.astimezone(timezone.utc)
                bridge_age = (datetime.now(timezone.utc) - sync_dt).total_seconds()
                result["last_modified"] = synced_at
                result["data_age_seconds"] = round(bridge_age, 1)
                if bridge_age < STALE_SECONDS_WARNING:
                    bridge_ok = True
            result["errors"].append("Bridge status found but no synced_at field" if not synced_at else "")
        except Exception as e:
            result["errors"].append("Cannot read ea_bridge_status.json: " + str(e))
    else:
        result["errors"].append("ea_bridge_status.json not found at " + str(EA_BRIDGE_STATUS))

    # --- 2) Read price from live data CSV ---
    if EA_LIVE_DATA.exists():
        # Update file_found to True if not already
        if not result["file_found"]:
            result["file_found"] = True
            result["file_path"] = str(EA_LIVE_DATA)
        try:
            stat = EA_LIVE_DATA.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            csv_age = (datetime.now(timezone.utc) - mtime).total_seconds()
            # Use CSV mod time as data_age if bridge status is missing
            if result["data_age_seconds"] is None:
                result["data_age_seconds"] = round(csv_age, 1)
                result["last_modified"] = mtime.isoformat()

            # Read last non-empty line for latest price
            with open(EA_LIVE_DATA, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # Find last non-empty line
            for line in reversed(lines):
                line = line.strip()
                if line:
                    parts = line.split(",")
                    # CSV format: timestamp,open,high,low,close,volume,...
                    # close price is at index 4
                    if len(parts) >= 5:
                        try:
                            close = float(parts[4])
                            result["bid"] = close
                            result["ask"] = close  # CSV only has close, use as both
                            result["price"] = close
                            result["file_readable"] = True
                            if not result["file_found"]:
                                result["file_found"] = True
                                result["file_path"] = str(EA_LIVE_DATA)
                        except (ValueError, TypeError):
                            result["errors"].append("Cannot parse close price from CSV: " + parts[4])
                    break

            # Check if CSV is fresh (file modified within threshold)
            if csv_age < STALE_SECONDS_WARNING:
                result["connected"] = True
            elif bridge_ok:
                result["connected"] = True
        except Exception as e:
            result["errors"].append("Cannot read live data CSV: " + str(e))
    else:
        if not result["file_found"]:
            result["errors"].append("Live data CSV not found at " + str(EA_LIVE_DATA))

    # Clean empty error strings
    result["errors"] = [e for e in result["errors"] if e]

    return result


def check_trading_dir():
    """Check arena/live_data/ directory for data files."""
    arena_live = ARENA_ROOT / "live_data"
    result = {"exists": False, "file_count": 0, "recent_files": [], "errors": []}
    if not arena_live.exists():
        result["errors"].append("Arena live_data directory not found: " + str(arena_live))
        return result
    result["exists"] = True

    try:
        for f in arena_live.iterdir():
            if f.is_file() and f.suffix.lower() in (".csv", ".txt", ".dat", ".json", ".log"):
                result["file_count"] += 1
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                age = (datetime.now(timezone.utc) - mtime).total_seconds()
                if age < 3600:  # modified in last hour
                    result["recent_files"].append(f.name)
    except Exception as e:
        result["errors"].append("Error scanning arena live_data dir: " + str(e))

    return result


def check_project_dir():
    """Check that trading project directory and server_file.py exist."""
    result = {"exists": False, "server_exists": False, "errors": []}
    if not TRADING_PROJECT_DIR.exists():
        result["errors"].append("Trading project dir not found: " + str(TRADING_PROJECT_DIR))
        return result
    result["exists"] = True
    if not TRADING_SERVER_PY.exists():
        result["errors"].append("server_file.py not found at " + str(TRADING_SERVER_PY))
        return result
    result["server_exists"] = True
    return result


# === Auto-restart ===

def restart_server():
    """Attempt to restart server_file.py."""
    action_msg = ""
    try:
        # Determine python binary
        python_bin = str(VENV_PYTHON) if VENV_PYTHON.exists() else "python3"
        script_path = str(TRADING_SERVER_PY)

        # Build restart command
        cmd = f"cd {TRADING_PROJECT_DIR} && nohup {python_bin} {script_path} > /tmp/trading_server.log 2>&1 &"

        subprocess.Popen(cmd, shell=True, executable="/bin/bash")
        action_msg = "auto-restart: " + python_bin + " " + script_path
        time.sleep(2)  # brief wait to let it start

        # Verify it started
        proc = subprocess.run(
            ["pgrep", "-f", "python3.*server_file\\.py"],
            capture_output=True, text=True
        )
        if proc.returncode == 0:
            action_msg += " [STARTED OK]"
        else:
            action_msg += " [START FAILED - process not found after restart]"
    except Exception as e:
        action_msg = "auto-restart FAILED: " + str(e)

    return action_msg


# === Heartbeat Builder ===

def build_heartbeat(server_proc, ea_data, trading_dir, project_dir, auto_actions):
    """Build the heartbeat JSON."""
    now = datetime.now(timezone.utc).isoformat()
    critical_issues = []
    high_issues = []
    health_score = 100

    connected = ea_data.get("connected", False)
    price = ea_data.get("price", 0.0)
    age = ea_data.get("data_age_seconds")

    # === Project dir check ===
    if not project_dir["exists"]:
        critical_issues.append("Trading project directory missing: " + str(TRADING_PROJECT_DIR))
        health_score -= 30
    elif not project_dir["server_exists"]:
        critical_issues.append("server_file.py not found in project directory")
        health_score -= 20

    # === Process check ===
    if not server_proc["running"]:
        critical_issues.append("server_file.py process is NOT running")
        health_score -= 40

    # === EA data file check ===
    if not ea_data["file_found"]:
        critical_issues.append("EA data not found - no EA data feed")
        health_score -= 40
        connected = False
    elif not ea_data.get("file_readable", False):
        critical_issues.append("EA data file unreadable or invalid")
        health_score -= 35
        connected = False
    elif price == PRICE_ZERO_THRESHOLD and not connected:
        critical_issues.append("EA price is 0.0 - EA disconnected from market")
        health_score -= 35

    # === Staleness check ===
    if age is not None:
        if age > STALE_SECONDS_CRITICAL:
            critical_issues.append("EA data stale: " + str(int(age)) + "s since last update (>" + str(STALE_SECONDS_CRITICAL) + "s)")
            health_score -= 25
            connected = False
        elif age > STALE_SECONDS_WARNING:
            high_issues.append("EA data aging: " + str(int(age)) + "s since last update (>" + str(STALE_SECONDS_WARNING) + "s)")
            health_score -= 10

    # === Trading directory check ===
    if not trading_dir["exists"]:
        high_issues.append("Arena live_data directory not found: " + str(ARENA_ROOT / "live_data"))
        health_score -= 5

    # === Collect check errors ===
    for err in (server_proc.get("errors", []) +
                ea_data.get("errors", []) +
                trading_dir.get("errors", []) +
                project_dir.get("errors", [])):
        if err not in critical_issues and err not in high_issues:
            high_issues.append(err)
            health_score -= 3

    # === Determine status ===
    health_score = max(0, min(100, health_score))

    if critical_issues:
        status = "CRITICAL"
        emoji = "\U0001f534"  # red circle
    elif high_issues:
        status = "ATTENTION"
        emoji = "\U0001f7e1"  # yellow circle
    else:
        status = "HEALTHY"
        emoji = "\U0001f7e2"  # green circle

    heartbeat = {
        "plan_id": "trading-server",
        "name": "Trading Server",
        "timestamp": now,
        "health_score": health_score,
        "status": status,
        "status_emoji": emoji,
        "total_issues": len(critical_issues) + len(high_issues),
        "critical_issues": critical_issues,
        "high_issues": high_issues,
        "services": {
            "server": {
                "running": server_proc["running"],
                "pid": server_proc.get("pid")
            },
            "ea_data": {
                "price": price,
                "bid": ea_data.get("bid", 0.0),
                "ask": ea_data.get("ask", 0.0),
                "fresh": age is not None and age < STALE_SECONDS_WARNING,
                "data_age_seconds": age,
                "file_path": ea_data.get("file_path"),
                "last_modified": ea_data.get("last_modified")
            }
        },
        "auto_actions": auto_actions
    }

    return heartbeat


def _preserve_heartbeat_metadata(path, data):
    if path != HEARTBEAT_PATH:
        return data
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

def write_json(path, data):
    """Write JSON atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _preserve_heartbeat_metadata(path, data)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(path))


# === Main ===

def main():
    parser = argparse.ArgumentParser(description="Trading Server PLAN Monitor")
    parser.add_argument("--fix", action="store_true",
                        help="Attempt auto-restart of server_file.py if not running")
    parser.add_argument("--heartbeat-only", action="store_true",
                        help="Output only the heartbeat JSON to stdout")
    args = parser.parse_args()

    # Run all checks
    project_dir = check_project_dir()
    server_proc = check_server_process()
    ea_data = check_ea_data_json()
    trading_dir = check_trading_dir()

    auto_actions = []

    # Auto-restart if needed
    if args.fix and not server_proc["running"] and project_dir["server_exists"]:
        action = restart_server()
        auto_actions.append(action)
        # Re-check process after restart
        server_proc = check_server_process()

    # Build heartbeat
    heartbeat = build_heartbeat(server_proc, ea_data, trading_dir, project_dir, auto_actions)

    # Ensure output directory exists
    HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Write heartbeat
    write_json(HEARTBEAT_PATH, heartbeat)

    # Initialize command/response channel files if they don't exist
    if not COMMAND_PATH.exists():
        write_json(COMMAND_PATH, {
            "plan_id": "trading-server",
            "status": "idle",
            "last_command": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    if not RESPONSE_PATH.exists():
        write_json(RESPONSE_PATH, {
            "plan_id": "trading-server",
            "status": "idle",
            "last_response": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    # === Output ===
    if args.heartbeat_only:
        print(json.dumps(heartbeat, indent=2, ensure_ascii=False))
    else:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print("[{}] Trading Server Monitor".format(ts))
        print("  Status     : {} {} (score {})".format(
            heartbeat["status_emoji"], heartbeat["status"], heartbeat["health_score"]))
        print("  Process    : {} (pid {})".format(
            "RUNNING" if server_proc["running"] else "DOWN",
            server_proc.get("pid", "N/A")))
        print("  EA Data    : price={}, bid={}, fresh={}".format(
            heartbeat["services"]["ea_data"]["price"],
            heartbeat["services"]["ea_data"]["bid"],
            heartbeat["services"]["ea_data"]["fresh"]))
        print("  Data Age   : {}s".format(
            heartbeat["services"]["ea_data"]["data_age_seconds"]))
        print("  Data File  : {}".format(
            heartbeat["services"]["ea_data"]["file_path"]))
        print("  Trading Dir: {} ({} files, {} recent)".format(
            "OK" if trading_dir["exists"] else "MISSING",
            trading_dir["file_count"],
            len(trading_dir["recent_files"])))
        print("  Issues     : {} (critical={}, high={})".format(
            heartbeat["total_issues"],
            len(heartbeat["critical_issues"]),
            len(heartbeat["high_issues"])))

        for issue in heartbeat["critical_issues"]:
            print("  CRITICAL   : " + issue)
        for issue in heartbeat["high_issues"]:
            print("  HIGH       : " + issue)
        for action in auto_actions:
            print("  ACTION     : " + action)

        print("  Heartbeat  : " + str(HEARTBEAT_PATH))

    # Exit code: 0=healthy, 1=attention, 2=critical
    if heartbeat["status"] == "CRITICAL":
        return 2
    elif heartbeat["status"] == "ATTENTION":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
