#!/usr/bin/env python3
"""
AC5: Operational Patrol

Automatically checks functional health of all registered Business Units.
Reads BU registry, checks each BU's actual health data, reports findings.

Usage:
  python3 operational_patrol.py              # Check all BUs
  python3 operational_patrol.py --bu arena   # Check specific BU
  python3 operational_patrol.py --json       # Output JSON
  python3 operational_patrol.py --report     # Generate report file

This patrol checks FUNCTIONAL health (do rules hold?), not just PROCESS health (is it alive?).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))
COMPANY_DIR = Path.home() / ".hermes" / "company"
REGISTRY_DIR = Path.home() / ".hermes" / "plan_registry"
REPORT_PATH = Path.home() / ".hermes" / "process" / "operational_patrol_report.json"
ARENA_REPORT_PATH = Path("<ARENA_ROOT>/arena/arena_control/plan_agent_report.json")
ARENA_CONTESTANTS = Path("<ARENA_ROOT>/arena/contestants")
MODULES = ["gpt_5.5", "opus_4.6", "opus_4.7", "deepseek_v4_pro", "mimo-v2-pro"]
TARGET_PER_MODULE = 100


def load_bu_registry() -> dict:
    path = COMPANY_DIR / "business_unit_registry.json"
    return json.loads(path.read_text())


def check_arena_functional_health() -> dict:
    """Check arena's functional health from plan_agent_report.json services."""
    now = datetime.now(TZ)

    result = {
        "bu_id": "arena",
        "bu_name": "百大交易競技場",
        "checked_at": now.isoformat(),
        "process_health": "unknown",
        "functional_health": "unknown",
        "user_visible_health": "unknown",
        "checks": [],
        "issues": [],
        "modules": {},
        "active_deficit_total": 0,
    }

    # 1. Process health: read from plan_agent_report.json services
    if ARENA_REPORT_PATH.exists():
        try:
            report = json.loads(ARENA_REPORT_PATH.read_text())
            services = report.get("services", [])
            all_running = True
            svc_details = []
            for svc in services:
                name = svc.get("name", "unknown")
                # Only check "running" field if it exists (some services like dashboard/system don't have it)
                if "running" in svc:
                    running = svc["running"]
                    svc_details.append({"name": name, "running": running})
                    if not running:
                        all_running = False
                else:
                    svc_details.append({"name": name, "running": "n/a"})

            result["process_health"] = "alive" if all_running else "partial"
            result["checks"].append({
                "check": "plan_agent_report_services",
                "all_running": all_running,
                "services": svc_details,
                "source": "plan_agent_report.json",
            })
            if not all_running:
                result["issues"].append("Some arena services not running")
        except Exception as e:
            result["process_health"] = "error"
            result["issues"].append(f"Failed to read plan_agent_report.json: {e}")
    else:
        result["process_health"] = "no_report"
        result["issues"].append("plan_agent_report.json not found")

    # 2. Functional health: per-module contestant counts
    if ARENA_REPORT_PATH.exists():
        try:
            report = json.loads(ARENA_REPORT_PATH.read_text())
            svc = next((s for s in report.get("services", []) if s["name"] == "arena_simulator"), None)
            if svc and svc.get("running"):
                details = svc.get("details", {})
                strategy_counts = details.get("strategy_counts", {})
                eliminated_counts = details.get("eliminated_counts", {})
                total_strategies = details.get("total_strategies", 0)
                target_total = details.get("target_total", 500)

                total_deficit = 0
                for mod in MODULES:
                    active = strategy_counts.get(mod, 0)
                    eliminated = eliminated_counts.get(mod, 0)
                    deficit = TARGET_PER_MODULE - active
                    total_deficit += max(0, deficit)

                    result["modules"][mod] = {
                        "active": active,
                        "eliminated": eliminated,
                        "target": TARGET_PER_MODULE,
                        "deficit": max(0, deficit),
                    }

                result["checks"].append({
                    "check": "contestant_counts_per_module",
                    "total_strategies": total_strategies,
                    "target_total": target_total,
                    "active_deficit_total": total_deficit,
                    "modules": result["modules"],
                })

                result["active_deficit_total"] = total_deficit

                if total_deficit > 0:
                    result["functional_health"] = "degraded"
                    result["issues"].append(
                        f"active_deficit_total={total_deficit} "
                        f"(total={total_strategies}, target={target_total})"
                    )
                else:
                    result["functional_health"] = "healthy"
            else:
                result["functional_health"] = "unknown"
                result["issues"].append("arena_simulator service not found or not running")
        except Exception as e:
            result["functional_health"] = "error"
            result["issues"].append(f"Failed to parse arena_simulator data: {e}")
    else:
        result["functional_health"] = "unknown"
        result["issues"].append("plan_agent_report.json not accessible")

    # 3. User-visible health
    if result["functional_health"] == "degraded":
        result["user_visible_health"] = "needs_review"
    elif result["functional_health"] == "healthy":
        result["user_visible_health"] = "healthy"
    else:
        result["user_visible_health"] = "unknown"

    # 4. False health check
    result["false_health_alert"] = (
        result["process_health"] == "alive"
        and result["functional_health"] == "degraded"
    )

    return result


def check_generic_bu(bu_id: str, bu_config: dict) -> dict:
    """Generic health check for BUs without specific checker."""
    now = datetime.now(TZ)
    return {
        "bu_id": bu_id,
        "bu_name": bu_config.get("name", bu_id),
        "checked_at": now.isoformat(),
        "process_health": bu_config.get("process_health", "unknown"),
        "functional_health": bu_config.get("functional_health", "unknown"),
        "user_visible_health": bu_config.get("user_visible_health", "unknown"),
        "checks": [],
        "issues": ["No specific health checker defined for this BU"],
        "false_health_alert": False,
    }


# BU-specific health checkers
BU_CHECKERS = {
    "arena": check_arena_functional_health,
}


def patrol_all(target_bu: str = None) -> dict:
    """Run operational patrol on all (or specific) BUs."""
    now = datetime.now(TZ)
    registry = load_bu_registry()

    report = {
        "patrol_at": now.isoformat(),
        "patrol_type": "operational",
        "bu_count": 0,
        "results": [],
        "false_health_alerts": [],
        "overall_status": "unknown",
    }

    for bu_id, bu_config in registry.get("business_units", {}).items():
        if target_bu and bu_id != target_bu:
            continue

        checker = BU_CHECKERS.get(bu_id, check_generic_bu)
        if bu_id in BU_CHECKERS:
            result = checker()
        else:
            result = checker(bu_id, bu_config)
        report["results"].append(result)

        if result.get("false_health_alert"):
            report["false_health_alerts"].append({
                "bu_id": bu_id,
                "reason": f"process={result['process_health']} but functional={result['functional_health']}",
            })

    report["bu_count"] = len(report["results"])

    # Overall status
    all_healthy = all(r.get("functional_health") == "healthy" for r in report["results"])
    any_degraded = any(r.get("functional_health") == "degraded" for r in report["results"])
    if all_healthy:
        report["overall_status"] = "all_healthy"
    elif any_degraded:
        report["overall_status"] = "degraded"
    else:
        report["overall_status"] = "mixed"

    return report


def format_report(report: dict) -> str:
    """Format patrol report as readable text."""
    lines = []
    lines.append("Operational Patrol Report")
    lines.append(f"Time: {report['patrol_at'][:19]}")
    lines.append(f"BUs checked: {report['bu_count']}")
    lines.append(f"Overall: {report['overall_status']}")
    lines.append("")

    for result in report["results"]:
        lines.append(f"### {result['bu_name']} ({result['bu_id']})")
        lines.append(f"  Process Health: {result['process_health']}")
        lines.append(f"  Functional Health: {result['functional_health']}")
        lines.append(f"  User-Visible Health: {result['user_visible_health']}")
        if result.get("active_deficit_total", 0) > 0:
            lines.append(f"  Active Deficit Total: {result['active_deficit_total']}")
        if result.get("false_health_alert"):
            lines.append(f"  WARNING: FALSE HEALTH ALERT: process alive but functional degraded!")
        if result.get("modules"):
            lines.append(f"  Modules:")
            for mod, data in result["modules"].items():
                lines.append(
                    f"    {mod}: active={data['active']} "
                    f"eliminated={data['eliminated']} "
                    f"target={data['target']} "
                    f"deficit={data['deficit']}"
                )
        if result.get("issues"):
            lines.append(f"  Issues:")
            for issue in result["issues"]:
                lines.append(f"    - {issue}")
        lines.append("")

    if report["false_health_alerts"]:
        lines.append("### False Health Alerts")
        for alert in report["false_health_alerts"]:
            lines.append(f"  WARNING: {alert['bu_id']}: {alert['reason']}")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Operational Patrol")
    parser.add_argument("--bu", help="Check specific BU")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--report", action="store_true", help="Save report file")
    args = parser.parse_args()

    report = patrol_all(target_bu=args.bu)

    if args.report:
        REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"Report saved: {REPORT_PATH}")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_report(report))


if __name__ == "__main__":
    main()
