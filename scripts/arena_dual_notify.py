#!/usr/bin/env python3
"""Dual notification: stdout + Telegram + JSONL log."""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

LEVEL_EMOJI = {
    "info": "ℹ️",
    "warning": "⚠️",
    "critical": "🚨",
    "dispute": "⚔️",
}

CHAT_ID = "6823341162"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPT_DIR, "arena_notify_log.jsonl")
ENV_PATH = os.path.expanduser("~/.hermes/.env")


def load_env_token():
    """Read ARENA_BOT_TOKEN from ~/.hermes/.env. Fail closed if missing.

    Arena notifications must not fall back to TELEGRAM_BOT_TOKEN because that
    token is routed to the Hermes brain bot.
    """
    try:
        with open(ENV_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                if key.strip() == "ARENA_BOT_TOKEN":
                    return val.strip().strip('"').strip("'")
    except Exception as e:
        print(f"[warn] Could not read {ENV_PATH}: {e}", file=sys.stderr)
    return os.environ.get("ARENA_BOT_TOKEN", "")

def send_telegram(token, text):
    """Send message via Telegram Bot API."""
    if not token:
        print("[warn] No ARENA_BOT_TOKEN set; skipping arena Telegram.", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        print(f"[warn] Telegram send failed: {e}", file=sys.stderr)
    return False


def append_log(timestamp, level, message):
    """Append one JSON line to the log file."""
    try:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps({"timestamp": timestamp, "level": level, "message": message}) + "\n")
    except Exception as e:
        print(f"[warn] Could not write log: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Send notification to stdout + Telegram")
    parser.add_argument("message", help="Message text")
    parser.add_argument("--level", choices=list(LEVEL_EMOJI.keys()), default="info",
                        help="Notification level (default: info)")
    args = parser.parse_args()

    level = args.level
    message = args.message
    emoji = LEVEL_EMOJI.get(level, "")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    formatted = f"{emoji} [{level.upper()}] {ts}: {message}"

    # 1) stdout
    print(formatted)

    # 2) Telegram
    send_telegram(load_env_token(), formatted)

    # 3) JSONL log
    append_log(ts, level, message)


if __name__ == "__main__":
    main()
