#!/usr/bin/env python3
"""
HM4: Native Heartbeat Writer

Reusable module for bots to write their own heartbeats.
Follows HEARTBEAT_METADATA_STANDARD v1.0.

Usage in bot code:
    from heartbeat_writer import HeartbeatWriter
    hb = HeartbeatWriter("hermes-tg-bot")
    hb.write(status="SELF_REPORTED", health_source="self_reported")

Features:
- Atomic write (tmp + rename)
- Follows metadata standard (13 fields)
- Configurable output path
- Never writes tokens/secrets
- Failure-safe (catches all exceptions)
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

TZ = timezone(timedelta(hours=8))
DEFAULT_REGISTRY_DIR = Path.home() / ".hermes" / "plan_registry"


class HeartbeatWriter:
    """Write heartbeat JSON for a PLAN module."""

    def __init__(
        self,
        plan_id: str,
        registry_dir: Optional[Path] = None,
        trust_level: str = "self",
        external_verified: bool = False,
    ):
        self.plan_id = plan_id
        self.registry_dir = Path(registry_dir) if registry_dir else DEFAULT_REGISTRY_DIR
        self.heartbeat_path = self.registry_dir / f"{plan_id.replace('-', '_')}_heartbeat.json"
        self.trust_level = trust_level
        self.external_verified = external_verified
        self._start_time = time.time()
        self._message_count = 0
        self._error_count = 0

    def record_message(self):
        """Call this each time the bot processes a message."""
        self._message_count += 1

    def record_error(self):
        """Call this each time the bot encounters an error."""
        self._error_count += 1

    def write(
        self,
        status: str = "SELF_REPORTED",
        health_source: str = "self_reported",
        confidence: str = "medium",
        extra: Optional[dict] = None,
    ) -> bool:
        """Write heartbeat to file. Returns True on success.

        Args:
            status: One of SELF_REPORTED / HEALTHY / STALE / CRITICAL / UNKNOWN
            health_source: self_reported / external_verified / cross_checked / manual_observed
            confidence: high / medium / low / none
            extra: Additional fields to include
        """
        try:
            now = datetime.now(TZ)
            uptime = int(time.time() - self._start_time)

            heartbeat = {
                "plan_id": self.plan_id,
                "timestamp": now.isoformat(),
                "status": status,
                "health_source": health_source,
                "trust_level": self.trust_level,
                "external_verified": self.external_verified,
                "confidence": confidence,
                "review_required": False,
                "uptime_seconds": uptime,
                "messages_processed": self._message_count,
                "errors_recent": self._error_count,
            }

            if extra:
                heartbeat.update(extra)

            # Atomic write: write to .tmp then rename
            tmp_path = self.heartbeat_path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(heartbeat, indent=2, ensure_ascii=False))
            tmp_path.rename(self.heartbeat_path)

            return True

        except Exception as e:
            # Never crash the bot for heartbeat failure
            return False

    def write_custom(self, data: dict) -> bool:
        """Write a fully custom heartbeat dict. Use with caution."""
        try:
            tmp_path = self.heartbeat_path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            tmp_path.rename(self.heartbeat_path)
            return True
        except Exception:
            return False


# Standalone usage
if __name__ == "__main__":
    import sys

    plan_id = sys.argv[1] if len(sys.argv) > 1 else "test-heartbeat"
    hb = HeartbeatWriter(plan_id)
    ok = hb.write(status="SELF_REPORTED", extra={"test": True})
    print(f"Heartbeat write: {'OK' if ok else 'FAILED'} → {hb.heartbeat_path}")
