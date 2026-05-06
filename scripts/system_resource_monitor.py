#!/usr/bin/env python3
"""
System Resource Monitor
=======================
Monitors disk, memory, network, WSL mount, and process counts.
Outputs JSON heartbeat to ~/.hermes/plan_registry/system_resource_heartbeat.json

Usage:
    python3 system_resource_monitor.py            # Full check with terminal output
    python3 system_resource_monitor.py --heartbeat-only  # JSON output only
"""

import subprocess
import json
import os
import sys
import re
from datetime import datetime, timezone


HEARTBEAT_PATH = os.path.expanduser("~/.hermes/plan_registry/system_resource_heartbeat.json")


def check_disk():
    """Check disk usage of / filesystem."""
    result = {"total": "?", "used": "?", "percent": 0, "status": "ok"}
    try:
        out = subprocess.check_output(["df", "-B1", "/"], text=True, timeout=10)
        lines = out.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            # Filesystem  1B-blocks    Used Available Use% Mounted on
            total_bytes = int(parts[1])
            used_bytes = int(parts[2])
            percent = int(parts[4].replace("%", ""))

            result["total"] = _fmt_bytes(total_bytes)
            result["used"] = _fmt_bytes(used_bytes)
            result["percent"] = percent

            if percent >= 90:
                result["status"] = "critical"
            elif percent >= 80:
                result["status"] = "warning"
            else:
                result["status"] = "ok"
    except Exception as e:
        result["status"] = "critical"
        result["error"] = str(e)
    return result


def check_memory():
    """Check memory usage via /proc/meminfo."""
    result = {"total": "?", "available": "?", "percent": 0, "status": "ok"}
    try:
        meminfo = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    meminfo[key] = int(parts[1])  # in kB

        total_kb = meminfo.get("MemTotal", 0)
        available_kb = meminfo.get("MemAvailable", 0)

        if total_kb == 0:
            raise RuntimeError("Could not read MemTotal from /proc/meminfo")

        total_bytes = total_kb * 1024
        avail_bytes = available_kb * 1024
        percent = round((1 - avail_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0

        result["total"] = _fmt_bytes(total_bytes)
        result["available"] = _fmt_bytes(avail_bytes)
        result["percent"] = percent

        avail_mb = avail_bytes / (1024 * 1024)
        if avail_mb < 500:
            result["status"] = "critical"
        elif avail_mb < 1024:
            result["status"] = "warning"
        else:
            result["status"] = "ok"
    except Exception as e:
        result["status"] = "critical"
        result["error"] = str(e)
    return result


def check_network():
    """Ping 8.8.8.8 to verify internet connectivity."""
    result = {"reachable": False, "latency_ms": 0, "status": "ok"}
    try:
        out = subprocess.check_output(
            ["ping", "-c", "3", "-W", "3", "8.8.8.8"],
            text=True, stderr=subprocess.STDOUT, timeout=15
        )
        match = re.search(r"min/avg/max/mdev\s*=\s*[\d.]+/([\d.]+)/", out)
        if match:
            result["latency_ms"] = round(float(match.group(1)), 2)
        result["reachable"] = True
        result["status"] = "ok"
    except Exception:
        result["reachable"] = False
        result["status"] = "critical"
    return result


def check_wsl_mount():
    """Check if /mnt/c/ is accessible (WSL Windows filesystem)."""
    result = {"accessible": False, "status": "ok"}
    mount_path = "/mnt/c/"
    try:
        if os.path.isdir(mount_path):
            entries = os.listdir(mount_path)
            result["accessible"] = len(entries) > 0
        else:
            result["accessible"] = False
    except Exception:
        result["accessible"] = False

    if not result["accessible"]:
        result["status"] = "warning"
    else:
        result["status"] = "ok"
    return result


def check_process_count():
    """Count python processes — potential zombie/leak detection."""
    result = {"count": 0, "status": "ok"}
    try:
        out = subprocess.check_output(
            ["pgrep", "-c", "-f", "python"],
            text=True, stderr=subprocess.STDOUT, timeout=10
        )
        result["count"] = int(out.strip())
    except subprocess.CalledProcessError:
        result["count"] = 0
    except Exception:
        result["count"] = -1

    if result["count"] > 500:
        result["status"] = "warning"
    else:
        result["status"] = "ok"
    return result


def _fmt_bytes(n):
    """Format bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def compute_overall(disk, memory, network, wsl_mount, proc):
    """Compute overall status, health score, and issues list."""
    issues = []
    score = 100
    statuses = []

    statuses.append(disk["status"])
    if disk["status"] == "critical":
        issues.append(f"DISK CRITICAL: {disk['percent']}% used ({disk['used']}/{disk['total']})")
        score -= 30
    elif disk["status"] == "warning":
        issues.append(f"DISK WARNING: {disk['percent']}% used ({disk['used']}/{disk['total']})")
        score -= 15

    statuses.append(memory["status"])
    if memory["status"] == "critical":
        issues.append(f"MEMORY CRITICAL: only {memory['available']} available")
        score -= 30
    elif memory["status"] == "warning":
        issues.append(f"MEMORY WARNING: only {memory['available']} available")
        score -= 15

    statuses.append(network["status"])
    if network["status"] == "critical":
        issues.append("NETWORK CRITICAL: cannot reach 8.8.8.8")
        score -= 30

    statuses.append(wsl_mount["status"])
    if wsl_mount["status"] == "warning":
        issues.append("WSL MOUNT WARNING: /mnt/c/ not accessible")
        score -= 10

    statuses.append(proc["status"])
    if proc["status"] == "warning":
        issues.append(f"PROCESS WARNING: {proc['count']} python processes running")
        score -= 10

    score = max(0, min(100, score))

    if "critical" in statuses:
        overall = "CRITICAL"
    elif "warning" in statuses:
        overall = "WARNING"
    else:
        overall = "HEALTHY"

    return overall, score, issues


def run_monitor(heartbeat_only=False):
    """Run all checks and produce the heartbeat JSON."""
    disk = check_disk()
    memory = check_memory()
    network = check_network()
    wsl_mount = check_wsl_mount()
    proc = check_process_count()

    overall, score, issues = compute_overall(disk, memory, network, wsl_mount, proc)

    heartbeat = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disk": disk,
        "memory": memory,
        "network": network,
        "wsl_mount": wsl_mount,
        "process_count": proc["count"],
        "overall_status": overall,
        "health_score": score,
        "issues": issues,
    }

    os.makedirs(os.path.dirname(HEARTBEAT_PATH), exist_ok=True)
    with open(HEARTBEAT_PATH, "w") as f:
        json.dump(heartbeat, f, indent=2)

    if heartbeat_only:
        print(json.dumps(heartbeat, indent=2))
    else:
        print("=" * 60)
        print("  SYSTEM RESOURCE MONITOR")
        print("=" * 60)
        print(f"  Timestamp : {heartbeat['timestamp']}")
        print(f"  Status    : {overall}  (score: {score}/100)")
        print("-" * 60)

        d_icon = {"ok": " OK ", "warning": "WARN", "critical": "CRIT"}[disk["status"]]
        print(f"  DISK      : [{d_icon}] {disk['percent']}% used -- {disk['used']} / {disk['total']}")

        m_icon = {"ok": " OK ", "warning": "WARN", "critical": "CRIT"}[memory["status"]]
        print(f"  MEMORY    : [{m_icon}] {memory['percent']}% used -- {memory['available']} free of {memory['total']}")

        n_icon = " OK " if network["reachable"] else "CRIT"
        lat = f"{network['latency_ms']}ms" if network["reachable"] else "N/A"
        print(f"  NETWORK   : [{n_icon}] reachable={network['reachable']}  latency={lat}")

        w_icon = " OK " if wsl_mount["accessible"] else "WARN"
        print(f"  WSL MOUNT : [{w_icon}] /mnt/c/ accessible={wsl_mount['accessible']}")

        p_icon = " OK " if proc["status"] == "ok" else "WARN"
        print(f"  PROCESSES : [{p_icon}] {proc['count']} python processes")

        print("-" * 60)
        if issues:
            print("  ISSUES:")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print("  No issues detected.")
        print("=" * 60)
        print(f"  Heartbeat written to: {HEARTBEAT_PATH}")
        print("=" * 60)

    return heartbeat


if __name__ == "__main__":
    heartbeat_only = "--heartbeat-only" in sys.argv
    run_monitor(heartbeat_only=heartbeat_only)
