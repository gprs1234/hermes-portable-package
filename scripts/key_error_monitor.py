#!/usr/bin/env python3
"""
Key Rotator — Error-triggered auto rotation

在 Hermes cron 裡跑，偵測最近的 API 錯誤。
如果當前 active key 連續失敗，自動切換到下一個 standby key。

Usage:
  python3 key_error_monitor.py              # 檢查並自動 rotate
  python3 key_error_monitor.py --dry-run    # 只檢查不切換
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))
POOL_PATH = Path.home() / ".hermes" / "key_pool.json"
CONFIG_PATH = Path.home() / ".hermes" / "config.yaml"
LOG_DIR = Path.home() / ".hermes" / "logs"

# Error patterns that indicate key exhaustion
KEY_ERROR_PATTERNS = [
    "401",
    "403",
    "Invalid token",
    "insufficient_quota",
    "rate_limit_exceeded",
    "quota exceeded",
    "billing",
    "payment required",
]


def load_pool() -> dict:
    return json.loads(POOL_PATH.read_text())


def save_pool(pool: dict):
    POOL_PATH.write_text(json.dumps(pool, indent=2, ensure_ascii=False))


def check_recent_errors(hours: int = 1) -> dict:
    """Check recent API error logs for key-related failures."""
    now = datetime.now(TZ)
    cutoff = now - timedelta(hours=hours)

    errors_by_provider = {}

    # Check Hermes agent logs for API errors
    for log_file in LOG_DIR.glob("*.jsonl"):
        try:
            for line in log_file.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    ts = entry.get("timestamp", "")
                    if ts and ts[:19] > cutoff.isoformat()[:19]:
                        msg = str(entry.get("error", "")) + str(entry.get("message", ""))
                        for pattern in KEY_ERROR_PATTERNS:
                            if pattern.lower() in msg.lower():
                                provider = entry.get("provider", "unknown")
                                if provider not in errors_by_provider:
                                    errors_by_provider[provider] = []
                                errors_by_provider[provider].append({
                                    "timestamp": ts,
                                    "error": msg[:200],
                                    "pattern": pattern,
                                })
                except json.JSONDecodeError:
                    continue
        except Exception:
            continue

    return errors_by_provider


def auto_rotate_on_error(dry_run: bool = False) -> dict:
    """Check errors and auto-rotate if needed."""
    pool = load_pool()
    now = datetime.now(TZ).isoformat()
    errors = check_recent_errors(hours=1)
    results = {"checked_at": now, "providers": {}, "rotations": []}

    for prov_name, prov_errors in errors.items():
        if prov_name not in pool["providers"]:
            continue

        prov = pool["providers"][prov_name]
        active_keys = [k for k in prov["keys"] if k["status"] == "active"]
        if not active_keys:
            continue

        current = active_keys[0]
        error_count = len(prov_errors)

        results["providers"][prov_name] = {
            "active_key": current["key_id"],
            "errors_in_last_hour": error_count,
            "needs_rotation": error_count >= 3,  # 3+ errors = rotate
        }

        if error_count >= 3:
            standby_keys = [k for k in prov["keys"] if k["status"] == "standby"]
            if not standby_keys:
                results["providers"][prov_name]["warning"] = "No standby keys!"
                continue

            if dry_run:
                results["providers"][prov_name]["action"] = f"WOULD rotate {current['key_id']} -> {standby_keys[0]['key_id']}"
            else:
                next_key = standby_keys[0]
                current["status"] = "exhausted"
                current["exhausted_at"] = now
                next_key["status"] = "active"
                next_key["activated_at"] = now

                # Update config.yaml
                from key_rotator import update_config_yaml
                update_config_yaml(prov_name, next_key["key"])

                pool["rotation_log"].append({
                    "timestamp": now,
                    "provider": prov_name,
                    "from_key": current["key_id"],
                    "to_key": next_key["key_id"],
                    "reason": f"auto-rotate: {error_count} errors in 1 hour",
                    "trigger": "error_monitor",
                })

                results["rotations"].append({
                    "provider": prov_name,
                    "from": current["key_id"],
                    "to": next_key["key_id"],
                    "errors": error_count,
                })

    if not dry_run:
        save_pool(pool)

    return results


def main():
    dry_run = "--dry-run" in sys.argv
    result = auto_rotate_on_error(dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result["rotations"]:
        print(f"\nRotated {len(result['rotations'])} key(s)!")
    elif not any(p.get("needs_rotation") for p in result["providers"].values()):
        print("\nAll keys healthy, no rotation needed.")


if __name__ == "__main__":
    main()
