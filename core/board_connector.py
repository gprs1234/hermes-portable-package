#!/usr/bin/env python3
"""
Board Connector - Bridges Board Bot decisions to Hermes CLI.

Data flow:
  Board Bot -> ~/projects/shared/board_decisions.json -> board_connector -> ~/.hermes/plan_registry/hermes_inbox.json

Usage:
  python3 board_connector.py check    - One-time check for new decisions
  python3 board_connector.py monitor  - Continuous monitoring (every 30s)
  python3 board_connector.py status   - Show current state
"""

import json
import os
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

# fcntl is POSIX-only; provide a no-op fallback so the module imports on Windows
try:
    import fcntl  # type: ignore
    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - Windows fallback
    _HAS_FCNTL = False

    class _FcntlShim:
        LOCK_SH = 0
        LOCK_UN = 0

        @staticmethod
        def flock(_fd, _op):
            return None

    fcntl = _FcntlShim()  # type: ignore

# Paths
BOARD_DECISIONS_FILE = Path.home() / "projects" / "shared" / "board_decisions.json"
HERMES_INBOX_FILE = Path.home() / ".hermes" / "plan_registry" / "hermes_inbox.json"
PROCESSED_IDS_FILE = Path.home() / ".hermes" / "plan_registry" / ".board_processed_ids.json"

# Cap processed_ids at the most recent N entries to bound disk footprint
PROCESSED_IDS_MAX = 10000


def load_processed_ids():
    """Load deque of already-processed decision IDs (bounded ring buffer).

    Returns a deque capped at PROCESSED_IDS_MAX. Order is preserved so
    that 'recent' IDs stay and the oldest fall off when the cap is reached.
    """
    if PROCESSED_IDS_FILE.exists():
        try:
            with open(PROCESSED_IDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                ids = data.get("processed_ids", [])
                if isinstance(ids, list):
                    return deque(ids, maxlen=PROCESSED_IDS_MAX)
                return deque(list(ids), maxlen=PROCESSED_IDS_MAX)
        except (json.JSONDecodeError, IOError):
            return deque(maxlen=PROCESSED_IDS_MAX)
    return deque(maxlen=PROCESSED_IDS_MAX)


def save_processed_ids(processed_ids):
    """Save deque (or set) of processed decision IDs."""
    PROCESSED_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(processed_ids, set):
        out = list(processed_ids)[-PROCESSED_IDS_MAX:]
    else:
        out = list(processed_ids)
    tmp = str(PROCESSED_IDS_FILE) + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"processed_ids": out}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, str(PROCESSED_IDS_FILE))


def poll_board():
    """
    Check board_decisions.json for new decisions.
    Returns list of new (unprocessed) decisions.

    Read uses a shared advisory lock so we don't see a half-written file
    while board_bot.py is mid-write.
    """
    if not BOARD_DECISIONS_FILE.exists():
        return []

    try:
        with open(BOARD_DECISIONS_FILE, "r", encoding="utf-8") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            except OSError:
                pass
            try:
                text = f.read()
            finally:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        data = json.loads(text)
    except (json.JSONDecodeError, IOError, OSError) as e:
        print(f"[ERROR] Failed to read board_decisions.json: {e}")
        return []

    decisions = data.get("decisions", [])
    processed_ids = load_processed_ids()
    processed_set = set(processed_ids)

    new_decisions = []
    for decision in decisions:
        decision_id = decision.get("id")
        if decision_id and decision_id not in processed_set:
            new_decisions.append(decision)

    return new_decisions


def format_for_hermes(decision):
    vote_result = decision.get("vote_result", "").lower()
    if vote_result in ("urgent", "emergency"):
        priority = "high"
    elif vote_result == "approved":
        priority = "normal"
    else:
        priority = "low"

    formatted = {
        "source": "board",
        "type": "decision",
        "decision_id": decision.get("id", ""),
        "topic": decision.get("topic", ""),
        "direction": decision.get("direction", ""),
        "action_items": decision.get("action_items", []),
        "vote_result": vote_result,
        "voters": decision.get("voters", {}),
        "priority": priority,
        "status": "pending",
        "received_at": datetime.now().isoformat(),
        "original_timestamp": decision.get("timestamp", ""),
    }
    return formatted


def write_to_inbox(formatted_decision):
    HERMES_INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)

    inbox_entries = []
    if HERMES_INBOX_FILE.exists():
        try:
            with open(HERMES_INBOX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    inbox_entries = data
                elif isinstance(data, dict):
                    inbox_entries = [data]
        except (json.JSONDecodeError, IOError):
            inbox_entries = []

    inbox_entries.append(formatted_decision)

    try:
        tmp = str(HERMES_INBOX_FILE) + f".tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(inbox_entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(HERMES_INBOX_FILE))
        return True
    except IOError as e:
        print(f"[ERROR] Failed to write to inbox: {e}")
        return False


def check_once():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Checking for new Board decisions...")

    new_decisions = poll_board()
    if not new_decisions:
        print("  No new decisions found.")
        return 0

    processed_ids = load_processed_ids()
    seen = set(processed_ids)
    count = 0

    for decision in new_decisions:
        decision_id = decision.get("id", "unknown")
        topic = decision.get("topic", "no topic")
        direction = decision.get("direction", "N/A")

        formatted = format_for_hermes(decision)

        if write_to_inbox(formatted):
            if decision_id not in seen:
                processed_ids.append(decision_id)
                seen.add(decision_id)
            count += 1
            print(f"  [NEW] Decision {decision_id}: {topic}")
            print(f"        Direction: {direction[:80]}")
            print(f"        Priority:  {formatted['priority']}")
            print(f"        Actions:   {', '.join(formatted['action_items'])}")
        else:
            print(f"  [ERROR] Failed to write decision {decision_id} to inbox")

    save_processed_ids(processed_ids)
    print(f"  => Processed {count} new decision(s).")
    return count


def monitor(interval=30):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Starting Board decision monitor (interval: {interval}s)")
    print(f"  Watching: {BOARD_DECISIONS_FILE}")
    print(f"  Inbox:    {HERMES_INBOX_FILE}")
    print("  Press Ctrl+C to stop.\n")

    try:
        while True:
            check_once()
            print()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[INFO] Monitor stopped by user.")


def show_status():
    processed_ids = load_processed_ids()

    print("Board Connector Status")
    print("=" * 50)
    print(f"  Board decisions file : {BOARD_DECISIONS_FILE}")
    print(f"  File exists          : {BOARD_DECISIONS_FILE.exists()}")
    print(f"  Hermes inbox         : {HERMES_INBOX_FILE}")
    print(f"  Inbox exists         : {HERMES_INBOX_FILE.exists()}")
    print(f"  Processed IDs file   : {PROCESSED_IDS_FILE}")
    print(f"  Processed decisions  : {len(processed_ids)}")

    if processed_ids:
        print()
        print("  Processed decision IDs (last 20):")
        for pid in list(processed_ids)[-20:]:
            print(f"    - {pid}")

    if HERMES_INBOX_FILE.exists():
        try:
            with open(HERMES_INBOX_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data if isinstance(data, list) else [data]
            pending = [e for e in entries if e.get("status") == "pending"]
            print()
            print(f"  Inbox entries total   : {len(entries)}")
            print(f"  Inbox entries pending : {len(pending)}")
        except (json.JSONDecodeError, IOError):
            print("  Inbox: (unreadable)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 board_connector.py <command>")
        print()
        print("Commands:")
        print("  check      One-time check for new Board decisions")
        print("  monitor    Continuous monitoring (every 30s)")
        print("  status     Show current connector state")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "check":
        count = check_once()
        sys.exit(0 if count >= 0 else 1)
    elif command == "monitor":
        interval = 30
        if len(sys.argv) > 2:
            try:
                interval = int(sys.argv[2])
            except ValueError:
                print(f"[ERROR] Invalid interval: {sys.argv[2]}")
                sys.exit(1)
        monitor(interval)
    elif command == "status":
        show_status()
    else:
        print(f"[ERROR] Unknown command: {command}")
        print("Use 'check', 'monitor', or 'status'")
        sys.exit(1)


if __name__ == "__main__":
    main()
