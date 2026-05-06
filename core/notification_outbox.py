#!/usr/bin/env python3
"""
Notification Outbox System for Telegram delivery failures.

Tries to send via Telegram API; on failure, queues to outbox.jsonl.
Supports flush (retry) and daily digest generation.

CLI:
  python3 notification_outbox.py send 'message' [severity]
  python3 notification_outbox.py flush
  python3 notification_outbox.py digest
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

SCRIPT_DIR = Path(__file__).resolve().parent
OUTBOX_FILE = SCRIPT_DIR / "outbox.jsonl"
DIGEST_FILE = SCRIPT_DIR / "daily_digest.md"

SEVERITY_ICONS = {
    "critical": "🔴",
    "high": "🟠",
    "normal": "🔵",
    "low": "⚪",
}


def _get_config():
    token = os.environ.get("HERMES_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", os.environ.get("CHAT_ID", ""))
    return token, chat_id


# Telegram MarkdownV2 reserved characters (must be escaped with backslash)
# Ref: https://core.telegram.org/bots/api#markdownv2-style
_MDV2_ESCAPE = r"_*[]()~`>#+-=|{}.!"


def _escape_markdown_v2(text: str) -> str:
    """Escape characters that have special meaning in Telegram MarkdownV2.

    Returns a string safe to send with parse_mode='MarkdownV2'.
    """
    if not text:
        return text
    out = []
    for ch in text:
        if ch in _MDV2_ESCAPE or ch == "\\":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _send_telegram(message: str, escape: bool = True) -> bool:
    """Send message via Telegram API. Returns True on success.

    By default the message is escaped for MarkdownV2 so that plan_ids
    containing ``_`` in plan IDs will not break parse_entities.
    """
    token, chat_id = _get_config()
    if not token or not chat_id or requests is None:
        return False

    payload = {"chat_id": chat_id}
    if escape:
        payload["text"] = _escape_markdown_v2(message)
        payload["parse_mode"] = "MarkdownV2"
    else:
        payload["text"] = message  # plain text, no parse mode

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200 and resp.json().get("ok", False):
            return True
        # Fall back to plain text on parse-entity failures
        if escape and resp.status_code == 400:
            payload_plain = {"chat_id": chat_id, "text": message}
            resp2 = requests.post(url, json=payload_plain, timeout=10)
            return resp2.status_code == 200 and resp2.json().get("ok", False)
        return False
    except Exception:
        return False


def _load_outbox() -> list[dict]:
    """Load all entries from outbox.jsonl."""
    if not OUTBOX_FILE.exists():
        return []
    entries = []
    for line in OUTBOX_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _save_entry(entry: dict):
    """Append a single entry to outbox.jsonl."""
    with open(OUTBOX_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _is_duplicate(message: str, severity: str = "normal", window_minutes: int = 5) -> bool:
    """Check if the same (severity, message) was queued within the dedup window.

    Dedup is now severity-aware so that the same text at CRITICAL and at NORMAL
    are treated as different events.
    """
    if not OUTBOX_FILE.exists():
        return False
    cutoff = time.time() - (window_minutes * 60)
    for line in OUTBOX_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if (entry.get("message") == message
                    and entry.get("severity", "normal") == severity
                    and entry.get("timestamp", 0) >= cutoff):
                return True
        except json.JSONDecodeError:
            continue
    return False


def _rewrite_outbox(entries: list[dict]):
    """Rewrite outbox.jsonl with given entries (used after successful flushes)."""
    with open(OUTBOX_FILE, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def send_or_queue(message: str, severity: str = "normal") -> str:
    """
    Try to send message via Telegram. On failure, queue to outbox.
    Returns: 'sent', 'queued', or 'duplicate'.
    """
    severity = severity.lower()
    if severity not in SEVERITY_ICONS:
        severity = "normal"

    # Dedup check (severity-aware)
    if _is_duplicate(message, severity):
        return "duplicate"

    icon = SEVERITY_ICONS[severity]
    formatted = f"{icon} [{severity.upper()}] {message}"

    if _send_telegram(formatted):
        return "sent"

    # Queue to outbox
    entry = {
        "message": message,
        "severity": severity,
        "formatted": formatted,
        "timestamp": time.time(),
        "queued_at": datetime.now().isoformat(),
        "retries": 0,
    }
    _save_entry(entry)
    return "queued"


def flush_outbox() -> tuple[int, int]:
    """
    Retry sending all queued notifications.
    Returns (sent_count, failed_count).
    """
    entries = _load_outbox()
    if not entries:
        return 0, 0

    remaining = []
    sent = 0
    failed = 0

    for entry in entries:
        if _send_telegram(entry.get("formatted", entry.get("message", ""))):
            sent += 1
        else:
            entry["retries"] = entry.get("retries", 0) + 1
            # Drop entries that have failed too many times (24h+ old with many retries)
            if entry["retries"] > 50:
                failed += 1
            else:
                remaining.append(entry)

    _rewrite_outbox(remaining)
    return sent, failed


def generate_digest() -> str:
    """Generate a daily digest markdown of today's queued notifications."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_ts = today_start.timestamp()

    entries = _load_outbox()
    today_entries = [e for e in entries if e.get("timestamp", 0) >= today_ts]

    # Also include recently sent ones from the outbox history
    lines = [
        f"# Daily Notification Digest",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d')}",
        "",
    ]

    if not today_entries:
        lines.append("No notifications queued today.")
    else:
        # Group by severity
        by_severity: dict[str, list] = {}
        for e in today_entries:
            sev = e.get("severity", "normal")
            by_severity.setdefault(sev, []).append(e)

        total = len(today_entries)
        lines.append(f"**Total queued:** {total}")
        lines.append("")

        for sev in ["critical", "high", "normal", "low"]:
            items = by_severity.get(sev, [])
            if not items:
                continue
            icon = SEVERITY_ICONS[sev]
            lines.append(f"## {icon} {sev.upper()} ({len(items)})")
            lines.append("")
            for e in items:
                ts = e.get("queued_at", "?")
                msg = e.get("message", "")
                retries = e.get("retries", 0)
                retry_info = f" (retries: {retries})" if retries > 0 else ""
                lines.append(f"- `{ts}`{retry_info} {msg}")
            lines.append("")

    content = "\n".join(lines)
    DIGEST_FILE.write_text(content)
    return content


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 notification_outbox.py send 'message' [severity]")
        print("  python3 notification_outbox.py flush")
        print("  python3 notification_outbox.py digest")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "send":
        if len(sys.argv) < 3:
            print("Error: message required")
            sys.exit(1)
        message = sys.argv[2]
        severity = sys.argv[3] if len(sys.argv) > 3 else "normal"
        result = send_or_queue(message, severity)
        print(f"Result: {result}")

    elif cmd == "flush":
        sent, failed = flush_outbox()
        remaining = len(_load_outbox())
        print(f"Flush complete: {sent} sent, {failed} dropped, {remaining} still queued")

    elif cmd == "digest":
        content = generate_digest()
        print(content)
        print(f"\nSaved to {DIGEST_FILE}")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
