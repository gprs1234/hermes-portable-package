#!/usr/bin/env python3
"""AI Dashboard 監控 — Flask app.py

Checks (in order):
  1. Is `app.py` process running? (pgrep)
  2. Is port 5000 accepting TCP connections? (socket.connect_ex — non-blocking)
  3. (optional) Does http://localhost:5000/ respond? (urllib)

Auto-restart with --fix flag.
Output heartbeat: ~/.hermes/plan_registry/ai_dashboard_heartbeat.json
"""
import json
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HEARTBEAT = Path.home() / ".hermes" / "plan_registry" / "ai_dashboard_heartbeat.json"
DASHBOARD_DIR = Path.home() / "projects" / "ai_visualization"
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "5000"))


def _process_running(pattern):
    try:
        r = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True, text=True, timeout=5,
        )
        return bool(r.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _port_open(host, port, timeout=3.0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _http_health(port, timeout=3.0):
    try:
        import urllib.request
        urllib.request.urlopen(f"http://localhost:{port}/", timeout=timeout)
        return True
    except Exception:
        return False


def check(fix=False):
    running = _process_running(r"python3.*app\.py")
    port_ok = _port_open("127.0.0.1", DASHBOARD_PORT)
    http_ok = _http_health(DASHBOARD_PORT) if port_ok else False

    if running and port_ok:
        status, score = ("HEALTHY", 100) if http_ok else ("HEALTHY", 90)
    elif not running:
        status, score = "DOWN", 0
    else:
        status, score = "DEGRADED", 60

    issues = []
    if not running:
        issues.append("app.py process not running")
    if running and not port_ok:
        issues.append(f"port {DASHBOARD_PORT} not accepting connections")
    if running and port_ok and not http_ok:
        issues.append("HTTP / endpoint did not respond (non-fatal)")

    hb = {
        "plan_id": "ai-dashboard",
        "name": "AI Visualization Dashboard",
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "health_score": score,
        "status_emoji": "🟢" if status == "HEALTHY" else ("🟡" if status == "DEGRADED" else "🔴"),
        "total_issues": len(issues),
        "issues": issues,
        "services": {
            "flask": {
                "running": running,
                f"port_{DASHBOARD_PORT}": port_ok,
                "http_health": http_ok,
            },
        },
    }

    if status != "HEALTHY" and fix and not running and DASHBOARD_DIR.exists():
        try:
            subprocess.Popen(
                ["python3", "app.py"],
                cwd=str(DASHBOARD_DIR),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            hb["auto_action"] = "attempted_restart"
        except Exception as e:
            hb["auto_action"] = f"restart_failed: {e}"

    HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(HEARTBEAT) + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(hb, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(HEARTBEAT))

    print(f"{hb['status_emoji']} Dashboard: {status} (score {score})")
    return hb


if __name__ == "__main__":
    check(fix="--fix" in sys.argv)
