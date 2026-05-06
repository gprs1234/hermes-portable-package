#!/usr/bin/env python3
"""POS Backend 監控 — Cloudflare Worker.

Active monitor:
  - If POS_BACKEND_URL is set (env var or ~/.hermes/.env), GET <url> with 10s
    timeout; record latency and status.
  - If unconfigured, write status=NOT_CONFIGURED so health_overview can skip
    instead of leaving a permanent 50/100 placeholder.

Cloudflare Workers can't be auto-restarted from here, so on DOWN we set
human_intervention_required and let notify_aggregate.py surface it.

Heartbeat output: ~/.hermes/plan_registry/pos_backend_heartbeat.json
"""
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HEARTBEAT = Path.home() / ".hermes" / "plan_registry" / "pos_backend_heartbeat.json"
ENV_FILE = Path.home() / ".hermes" / ".env"


def _resolve_url():
    """Get POS_BACKEND_URL from env var or ~/.hermes/.env."""
    url = os.environ.get("POS_BACKEND_URL", "").strip()
    if url:
        return url
    if ENV_FILE.exists():
        try:
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("POS_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
    return ""


def _write_atomic(hb):
    HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(HEARTBEAT) + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(hb, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(HEARTBEAT))


def check():
    pos_url = _resolve_url()

    if not pos_url:
        hb = {
            "plan_id": "pos-backend",
            "name": "POS Backend (Cloudflare Worker)",
            "timestamp": datetime.now().isoformat(),
            "status": "NOT_CONFIGURED",
            "health_score": 0,
            "status_emoji": "⚙️",
            "total_issues": 1,
            "issues": ["POS_BACKEND_URL 未設定。請在 ~/.hermes/.env 加入 POS_BACKEND_URL=https://your-worker.workers.dev"],
            "services": {"url": "not configured"},
            "human_intervention_required": True,
            "human_action_needed": "在 ~/.hermes/.env 設定 POS_BACKEND_URL 即可啟用真實監控",
            "exclude_from_overview": True,
        }
        _write_atomic(hb)
        print("⚙️ POS Backend: NOT_CONFIGURED (set POS_BACKEND_URL to enable)")
        return hb

    ctx = ssl.create_default_context()
    req = urllib.request.Request(pos_url, method="GET", headers={"User-Agent": "hermes-monitor/1.0"})
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            latency = round(time.time() - start, 3)
            ok = 200 <= resp.status < 300
            hb = {
                "plan_id": "pos-backend",
                "name": "POS Backend (Cloudflare Worker)",
                "timestamp": datetime.now().isoformat(),
                "status": "HEALTHY" if ok else "DEGRADED",
                "health_score": 100 if ok else 60,
                "status_emoji": "🟢" if ok else "🟡",
                "total_issues": 0 if ok else 1,
                "issues": [] if ok else [f"HTTP {resp.status}"],
                "services": {"url": pos_url, "latency_s": latency, "http_status": resp.status},
            }
    except urllib.error.HTTPError as e:
        hb = {
            "plan_id": "pos-backend",
            "name": "POS Backend (Cloudflare Worker)",
            "timestamp": datetime.now().isoformat(),
            "status": "DEGRADED" if e.code in (401, 403, 404) else "DOWN",
            "health_score": 40 if e.code in (401, 403, 404) else 0,
            "status_emoji": "🟡" if e.code in (401, 403, 404) else "🔴",
            "total_issues": 1,
            "issues": [f"HTTP {e.code}: {e.reason}"],
            "services": {"url": pos_url, "http_status": e.code},
            "human_intervention_required": e.code not in (401, 403, 404),
            "human_action_needed": "檢查 Cloudflare Workers dashboard" if e.code >= 500 else None,
        }
    except Exception as e:
        hb = {
            "plan_id": "pos-backend",
            "name": "POS Backend (Cloudflare Worker)",
            "timestamp": datetime.now().isoformat(),
            "status": "DOWN",
            "health_score": 0,
            "status_emoji": "🔴",
            "total_issues": 1,
            "issues": [f"連線失敗: {str(e)[:100]}"],
            "services": {"url": pos_url, "error": str(e)[:200]},
            "human_intervention_required": True,
            "human_action_needed": "檢查 Cloudflare Workers dashboard",
        }

    _write_atomic(hb)
    print(f"{hb['status_emoji']} POS Backend: {hb['status']}")
    return hb


if __name__ == "__main__":
    check()
