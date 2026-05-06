#!/usr/bin/env python3
"""
Hermes Notification Aggregator
Reads all *_heartbeat.json from ~/.hermes/plan_registry/
and produces a single aggregated summary (text or JSON).
Usage:
    python3 notify_aggregate.py          # human-readable summary
    python3 notify_aggregate.py --json   # JSON output
"""

import json
import os
import sys
import glob
from datetime import datetime, timezone, timedelta
from collections import defaultdict

HEARTBEAT_DIR = os.path.expanduser("~/.hermes/plan_registry")
TIME_WINDOW_MINUTES = 10

# ── Severity mapping ──────────────────────────────────────────────

CRITICAL_STATUSES = {"CRITICAL"}
WARNING_STATUSES  = {"WARNING", "DEGRADED", "UNKNOWN", "DOWN"}
HEALTHY_STATUSES  = {"HEALTHY", "OK"}
# Statuses to ignore entirely (PLAN tells us "skip me, I'm not configured yet")
SKIP_STATUSES     = {"NOT_CONFIGURED", "DISABLED", "UNREGISTERED"}

STATUS_EMOJI = {
    "CRITICAL": "🔴",
    "WARNING":  "🟡",
    "HEALTHY":  "🟢",
    "UNKNOWN":  "⚪",
}

def classify_status(raw_status: str) -> str:
    """Normalize a heartbeat status into HEALTHY / WARNING / CRITICAL / SKIP."""
    upper = (raw_status or "").upper()
    if upper in SKIP_STATUSES:
        return "SKIP"
    if upper in CRITICAL_STATUSES:
        return "CRITICAL"
    if upper in WARNING_STATUSES:
        return "WARNING"
    if upper in HEALTHY_STATUSES:
        return "HEALTHY"
    return "WARNING"  # anything unrecognised is treated as warning


def parse_ts(ts_str: str) -> datetime | None:
    """Parse an ISO-8601 timestamp, return aware UTC datetime or None."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def extract_name(data: dict, path: str) -> str:
    """Derive a human-friendly PLAN name from the heartbeat data."""
    for key in ("plan_id", "name", "service"):
        if key in data and data[key]:
            return str(data[key])
    # fallback: filename without _heartbeat.json
    base = os.path.basename(path)
    return base.replace("_heartbeat.json", "")


def extract_status(data: dict) -> str:
    """Pull the raw status string from the heartbeat JSON."""
    for key in ("status", "overall_status"):
        if key in data and data[key]:
            return str(data[key])
    return "UNKNOWN"


def extract_timestamp(data: dict) -> datetime | None:
    return parse_ts(data.get("timestamp", ""))


def extract_summary(data: dict, severity: str) -> str:
    """Build a one-line human summary of what's wrong (or right)."""
    if severity == "HEALTHY":
        return ""

    # Try structured fields
    issues = []
    for key in ("critical_issues", "high_issues"):
        for item in data.get(key, []):
            if isinstance(item, str):
                issues.append(item)
    if issues:
        return "; ".join(issues[:2])  # cap at 2 lines

    # Try message
    msg = data.get("message", "")
    if msg:
        return msg

    # Try human_action_needed
    action = data.get("human_action_needed", "")
    if action:
        return action[:80]

    # Try auto-fix result
    details = data.get("details", {})
    if isinstance(details, dict):
        reason = details.get("reason", "")
        if reason:
            return reason[:80]

    return "需要檢查"


def extract_auto_fixed(data: dict) -> bool:
    """Check if the heartbeat indicates an auto-fix was performed."""
    details = data.get("details", {})
    if isinstance(details, dict):
        af = details.get("auto_fix", {})
        if isinstance(af, dict):
            result = af.get("result", "").upper()
            if result == "FIXED":
                return True
        # top-level result
        result = details.get("result", "").upper()
        if "FIX" in result or "RESTART" in result:
            return True
    return False


# ── Core aggregation ──────────────────────────────────────────────

def load_heartbeats() -> list[dict]:
    """Load and normalise every *_heartbeat.json into a list of dicts."""
    pattern = os.path.join(HEARTBEAT_DIR, "*_heartbeat.json")
    entries = []
    now = datetime.now(timezone.utc)

    for fpath in sorted(glob.glob(pattern)):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        ts = extract_timestamp(data)
        raw_status = extract_status(data)
        severity = classify_status(raw_status)
        # Honour PLANs that ask to be skipped (e.g., POS Backend not configured)
        if severity == "SKIP" or data.get("exclude_from_overview"):
            continue
        name = extract_name(data, fpath)
        summary = extract_summary(data, severity)
        auto_fixed = extract_auto_fixed(data)

        entries.append({
            "name": name,
            "file": fpath,
            "status_raw": raw_status,
            "severity": severity,
            "timestamp": ts,
            "summary": summary,
            "auto_fixed": auto_fixed,
            "stale": (now - ts).total_seconds() > TIME_WINDOW_MINUTES * 60 if ts else True,
        })

    return entries


def aggregate(entries: list[dict]) -> dict:
    """
    Aggregate entries into a summary structure.
    Deduplicates: same severity + same 10-min window => merged message.
    """
    counts = {"HEALTHY": 0, "WARNING": 0, "CRITICAL": 0}
    issues = []      # non-healthy entries
    needs_human = [] # entries requiring human intervention

    for e in entries:
        counts[e["severity"]] = counts.get(e["severity"], 0) + 1
        if e["severity"] != "HEALTHY":
            issues.append(e)
        if e.get("stale") and e["severity"] == "CRITICAL":
            needs_human.append(e["name"])
        # Also check explicit flag
        raw = e.get("status_raw", "").upper()
        if "CRITICAL" in raw:
            needs_human.append(e["name"])

    # Deduplicate needs_human
    needs_human = list(dict.fromkeys(needs_human))

    # Group issues by (severity, window_bucket)
    # window_bucket = floor timestamp to 10-min intervals
    groups = defaultdict(list)
    for iss in issues:
        ts = iss["timestamp"]
        if ts:
            bucket = ts.replace(
                minute=(ts.minute // TIME_WINDOW_MINUTES) * TIME_WINDOW_MINUTES,
                second=0, microsecond=0
            )
        else:
            bucket = None
        key = (iss["severity"], bucket)
        groups[key].append(iss)

    return {
        "counts": counts,
        "issues": issues,
        "groups": dict(groups),
        "needs_human": needs_human,
        "total": len(entries),
    }


# ── Output formatters ─────────────────────────────────────────────

def format_text(agg: dict) -> str:
    """Produce the Telegram-friendly text summary."""
    counts = agg["counts"]
    total = agg["total"]
    issues = agg["issues"]

    # ── All healthy? ──────────────────────────────────────────────
    if counts["CRITICAL"] == 0 and counts["WARNING"] == 0:
        return f"🟢 全域健康 OK ({total} 個 PLAN 正常)"

    # ── Build header ──────────────────────────────────────────────
    parts = ["📊 Hermes 全域摘要", "━━━━━━━━━━━━━━"]

    status_line_parts = []
    if counts["HEALTHY"] > 0:
        status_line_parts.append(f"🟢 {counts['HEALTHY']} 個正常")
    if counts["WARNING"] > 0:
        status_line_parts.append(f"🟡 {counts['WARNING']} 個注意")
    if counts["CRITICAL"] > 0:
        status_line_parts.append(f"🔴 {counts['CRITICAL']} 個異常")
    parts.append(" | ".join(status_line_parts))
    parts.append("━━━━━━━━━━━━━━")

    # ── Deduped issue lines ───────────────────────────────────────
    # If 3+ of same severity, produce one aggregate line
    critical_issues = [i for i in issues if i["severity"] == "CRITICAL"]
    warning_issues  = [i for i in issues if i["severity"] == "WARNING"]

    issue_lines = []

    def emit_group(severity_label: str, group: list[dict]):
        if len(group) >= 3:
            names = ", ".join(e["name"] for e in group)
            issue_lines.append(
                f"{STATUS_EMOJI[severity_label]} {len(group)} 個 PLAN {severity_label}: {names}"
            )
        else:
            for e in group:
                suffix = ""
                if e["auto_fixed"]:
                    suffix = " (已自動修復)"
                elif e["summary"]:
                    suffix = f": {e['summary'][:60]}"
                issue_lines.append(f"{STATUS_EMOJI[severity_label]} {e['name']}{suffix}")

    emit_group("CRITICAL", critical_issues)
    emit_group("WARNING", warning_issues)

    parts.extend(issue_lines)
    parts.append("━━━━━━━━━━━━━━")

    # ── Needs human ───────────────────────────────────────────────
    if agg["needs_human"]:
        parts.append(f"需要你: {', '.join(agg['needs_human'])}")
    else:
        parts.append("需要你: 無")

    return "\n".join(parts)


def format_json(agg: dict) -> str:
    """Produce a JSON summary."""
    now = datetime.now(timezone.utc)
    out = {
        "timestamp": now.isoformat(),
        "total_plans": agg["total"],
        "counts": agg["counts"],
        "needs_human": agg["needs_human"],
        "issues": [],
    }
    for iss in agg["issues"]:
        out["issues"].append({
            "name": iss["name"],
            "severity": iss["severity"],
            "status_raw": iss["status_raw"],
            "summary": iss["summary"],
            "timestamp": iss["timestamp"].isoformat() if iss["timestamp"] else None,
            "auto_fixed": iss["auto_fixed"],
        })
    return json.dumps(out, ensure_ascii=False, indent=2)


# ── Main ──────────────────────────────────────────────────────────

def main():
    json_mode = "--json" in sys.argv

    entries = load_heartbeats()
    if not entries:
        msg = "⚠️ 沒有找到任何 heartbeat 檔案"
        if json_mode:
            print(json.dumps({"error": msg, "timestamp": datetime.now(timezone.utc).isoformat()},
                             ensure_ascii=False))
        else:
            print(msg)
        sys.exit(1)

    agg = aggregate(entries)

    if json_mode:
        print(format_json(agg))
    else:
        print(format_text(agg))


if __name__ == "__main__":
    main()
