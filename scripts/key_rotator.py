#!/usr/bin/env python3
"""
Key Rotator — API Key Pool Manager

功能:
  1. check  — 檢查所有 key 的用量
  2. rotate — 用量達 threshold 時自動切換
  3. status — 顯示所有 key 狀態
  4. dashboard — 產生用量看板 (MD)

Usage:
  python3 key_rotator.py status
  python3 key_rotator.py check --provider cdnipcs
  python3 key_rotator.py rotate --provider cdnipcs
  python3 key_rotator.py dashboard

自動輪換: 在 Hermes cron job 裡跑 check + rotate
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()
PORTABLE_HOME = Path(os.environ.get("HERMES_PORTABLE_HOME", Path.home() / ".hermes-portable")).expanduser()
POOL_PATH = Path(os.environ.get("HERMES_KEY_POOL", PORTABLE_HOME / "key_pool.json")).expanduser()
CONFIG_PATH = Path(os.environ.get("HERMES_CONFIG", HERMES_HOME / "config.yaml")).expanduser()
DASHBOARD_PATH = Path(os.environ.get("HERMES_KEY_DASHBOARD", HERMES_HOME / "process" / "key_usage_dashboard.md")).expanduser()


def load_pool() -> dict:
    return json.loads(POOL_PATH.read_text())


def save_pool(pool: dict):
    POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    POOL_PATH.write_text(json.dumps(pool, indent=2, ensure_ascii=False))


def resolve_key(key_entry: dict) -> str:
    """Resolve a key from an env var reference.

    Public key pools should store {"env": "OPENAI_API_KEY"} instead of raw
    {"key": "..."} values. Raw keys are still accepted for private legacy pools.
    """
    env_name = key_entry.get("env")
    if env_name:
        return os.environ.get(env_name, "")
    return key_entry.get("key", "")


def check_usage(provider: str = None) -> dict:
    """Check usage for all keys of a provider (or all providers)."""
    pool = load_pool()
    now = datetime.now(TZ).isoformat()

    results = {}
    providers_to_check = {provider: pool["providers"][provider]} if provider else pool["providers"]

    for prov_name, prov_config in providers_to_check.items():
        base_url = prov_config["base_url"]
        results[prov_name] = {"keys": [], "checked_at": now}

        for key_entry in prov_config["keys"]:
            if key_entry["status"] in ("exhausted", "revoked"):
                results[prov_name]["keys"].append({
                    "key_id": key_entry["key_id"],
                    "status": key_entry["status"],
                    "skipped": True,
                })
                continue

            # Try to check usage via API
            api_key = resolve_key(key_entry)
            if not api_key:
                results[prov_name]["keys"].append({
                    "key_id": key_entry["key_id"],
                    "status": key_entry["status"],
                    "error": f"missing env var {key_entry.get('env', 'key')}",
                })
                continue

            usage = query_usage(base_url, api_key)
            key_entry["usage"]["last_checked"] = now

            if usage.get("error"):
                results[prov_name]["keys"].append({
                    "key_id": key_entry["key_id"],
                    "status": key_entry["status"],
                    "error": usage["error"],
                })
            else:
                pct = usage.get("percentage", 0)
                key_entry["usage"]["percentage"] = pct
                key_entry["usage"]["requests_used"] = usage.get("requests_used")
                key_entry["usage"]["requests_limit"] = usage.get("requests_limit")
                key_entry["usage"]["tokens_used"] = usage.get("tokens_used")
                key_entry["usage"]["tokens_limit"] = usage.get("tokens_limit")

                results[prov_name]["keys"].append({
                    "key_id": key_entry["key_id"],
                    "status": key_entry["status"],
                    "percentage": pct,
                    "requests_used": usage.get("requests_used"),
                    "requests_limit": usage.get("requests_limit"),
                    "tokens_used": usage.get("tokens_used"),
                    "tokens_limit": usage.get("tokens_limit"),
                })

    save_pool(pool)
    return results


def query_usage(base_url: str, api_key: str) -> dict:
    """Query API for usage info. Returns dict with percentage or error."""
    try:
        # Try common usage endpoints
        endpoints = ["/usage", "/dashboard/billing/usage", "/v1/usage"]
        for endpoint in endpoints:
            url = f"{base_url.rstrip('/')}{endpoint}"
            result = subprocess.run(
                ["curl", "-s", "-H", f"Authorization: Bearer {api_key}", url],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                try:
                    data = json.loads(result.stdout)
                    # Try to extract usage info from response
                    if "usage" in data:
                        usage_data = data["usage"]
                        total = usage_data.get("total", 0)
                        limit = usage_data.get("limit", 1000)
                        pct = (total / limit * 100) if limit > 0 else 0
                        return {
                            "percentage": round(pct, 1),
                            "requests_used": total,
                            "requests_limit": limit,
                        }
                    elif "data" in data:
                        # Some APIs return {data: {usage: ...}}
                        usage_data = data["data"]
                        return {"percentage": 0, "raw": usage_data}
                except json.JSONDecodeError:
                    continue

        # If no endpoint works, return unknown
        return {"percentage": -1, "error": "usage endpoint not available"}

    except Exception as e:
        return {"percentage": -1, "error": str(e)}


def rotate(provider: str) -> dict:
    """Rotate to next standby key if current exceeds threshold."""
    pool = load_pool()
    threshold = pool.get("rotation_threshold", 0.95)
    now = datetime.now(TZ).isoformat()

    if provider not in pool["providers"]:
        return {"error": f"Provider {provider} not in pool"}

    prov = pool["providers"][provider]
    keys = prov["keys"]

    # Find current active key
    active_keys = [k for k in keys if k["status"] == "active"]
    if not active_keys:
        return {"error": "No active key found"}

    current = active_keys[0]
    current_pct = current["usage"].get("percentage", 0) or 0

    if current_pct < threshold * 100:
        return {
            "rotated": False,
            "reason": f"usage {current_pct}% < threshold {threshold*100}%",
            "current_key": current["key_id"],
        }

    # Find next standby key
    standby_keys = [k for k in keys if k["status"] == "standby"]
    if not standby_keys:
        return {"error": "No standby key available! All keys exhausted.", "rotated": False}

    next_key = standby_keys[0]

    # Rotate
    current["status"] = "exhausted"
    current["exhausted_at"] = now
    next_key["status"] = "active"
    next_key["activated_at"] = now

    # Update config.yaml
    update_config_yaml(provider, next_key)

    # Log rotation
    pool["rotation_log"].append({
        "timestamp": now,
        "provider": provider,
        "from_key": current["key_id"],
        "to_key": next_key["key_id"],
        "reason": f"usage {current_pct}% >= threshold {threshold*100}%",
    })

    save_pool(pool)

    return {
        "rotated": True,
        "from": current["key_id"],
        "to": next_key["key_id"],
        "usage_at_rotation": current_pct,
    }


def update_config_yaml(provider: str, key_entry: dict):
    """Update config.yaml for the given provider without writing raw keys."""
    config_path = CONFIG_PATH
    if not config_path.exists():
        return

    content = config_path.read_text()
    lines = content.split("\n")
    in_provider = False
    updated = False
    env_name = key_entry.get("env")
    raw_key = key_entry.get("key")

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{provider}:"):
            in_provider = True
        elif in_provider and stripped.startswith("apiKeyEnv:") and env_name:
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f"{indent}apiKeyEnv: {env_name}"
            updated = True
            in_provider = False
        elif in_provider and stripped.startswith("apiKey:"):
            # Extract indentation
            indent = line[: len(line) - len(line.lstrip())]
            if env_name:
                lines[i] = f"{indent}apiKeyEnv: {env_name}"
            else:
                lines[i] = f"{indent}apiKey: {raw_key}"
            updated = True
            in_provider = False
        elif in_provider and not stripped.startswith("#") and stripped and not stripped.startswith("-"):
            # Check if we've left the provider block
            if ":" in stripped and not stripped.startswith("apiKey"):
                in_provider = False

    if updated:
        config_path.write_text("\n".join(lines))


def generate_dashboard() -> str:
    """Generate key usage dashboard in markdown."""
    pool = load_pool()
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    threshold = pool.get("rotation_threshold", 0.95)

    lines = []
    lines.append("# API Key Usage Dashboard")
    lines.append(f"更新時間: {now}")
    lines.append(f"輪換閾值: {threshold*100:.0f}%")
    lines.append("")
    lines.append("| Provider | Key ID | Status | Usage | Requests | Tokens | Last Checked |")
    lines.append("|----------|--------|--------|-------|----------|--------|-------------|")

    for prov_name, prov_config in pool.get("providers", {}).items():
        for key in prov_config.get("keys", []):
            kid = key["key_id"]
            status = key["status"]
            usage = key.get("usage", {})
            pct = usage.get("percentage")
            pct_str = f"{pct}%" if pct is not None and pct >= 0 else "?"
            req = f"{usage.get('requests_used', '?')}/{usage.get('requests_limit', '?')}"
            tok = f"{usage.get('tokens_used', '?')}/{usage.get('tokens_limit', '?')}"
            checked = (usage.get("last_checked") or "?")[:16]

            # Status emoji
            if status == "active":
                if pct is not None and pct >= threshold * 100:
                    status_icon = "🔴"
                elif pct is not None and pct >= 80:
                    status_icon = "🟠"
                else:
                    status_icon = "🟢"
            elif status == "standby":
                status_icon = "⚪"
            elif status == "exhausted":
                status_icon = "⚫"
            else:
                status_icon = "❓"

            lines.append(f"| {prov_name} | {kid} | {status_icon} {status} | {pct_str} | {req} | {tok} | {checked} |")

    # Rotation log
    rotation_log = pool.get("rotation_log", [])
    if rotation_log:
        lines.append("")
        lines.append("## Rotation History")
        lines.append("")
        lines.append("| Time | Provider | From | To | Reason |")
        lines.append("|------|----------|------|-----|--------|")
        for entry in rotation_log[-10:]:  # Last 10
            lines.append(f"| {entry['timestamp'][:16]} | {entry['provider']} | {entry['from_key']} | {entry['to_key']} | {entry['reason']} |")

    # Action needed
    lines.append("")
    lines.append("## Status Summary")
    for prov_name, prov_config in pool.get("providers", {}).items():
        active = [k for k in prov_config["keys"] if k["status"] == "active"]
        standby = [k for k in prov_config["keys"] if k["status"] == "standby"]
        exhausted = [k for k in prov_config["keys"] if k["status"] == "exhausted"]
        pct = active[0]["usage"].get("percentage", "?") if active else "N/A"
        lines.append(f"- **{prov_name}**: active={len(active)}, standby={len(standby)}, exhausted={len(exhausted)}, usage={pct}%")
        if not standby and active:
            lines.append(f"  ⚠️ No standby keys! Add more keys before current one exhausts.")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Key Rotator — API Key Pool Manager")
    sub = parser.add_subparsers(dest="command")

    check_p = sub.add_parser("check", help="Check usage for all keys")
    check_p.add_argument("--provider", help="Specific provider")

    rotate_p = sub.add_parser("rotate", help="Rotate key if threshold exceeded")
    rotate_p.add_argument("--provider", required=True)

    sub.add_parser("status", help="Show all key statuses")
    sub.add_parser("dashboard", help="Generate usage dashboard")

    add_p = sub.add_parser("add", help="Add a new key to pool")
    add_p.add_argument("--provider", required=True)
    add_p.add_argument("--env", required=True, help="Environment variable that stores the real key")
    add_p.add_argument("--label", default="")

    args = parser.parse_args()

    if args.command == "check":
        results = check_usage(args.provider)
        print(json.dumps(results, indent=2, ensure_ascii=False))

    elif args.command == "rotate":
        result = rotate(args.provider)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "status":
        pool = load_pool()
        for prov_name, prov_config in pool["providers"].items():
            print(f"\n{prov_name}:")
            for key in prov_config["keys"]:
                pct = key["usage"].get("percentage", "?")
                print(f"  {key['key_id']}: {key['status']} | usage={pct}% | {key['label']}")

    elif args.command == "dashboard":
        md = generate_dashboard()
        DASHBOARD_PATH.write_text(md)
        print(f"Dashboard saved: {DASHBOARD_PATH}")
        print(md)

    elif args.command == "add":
        pool = load_pool()
        if args.provider not in pool["providers"]:
            print(f"Provider {args.provider} not found")
            sys.exit(1)
        new_key = {
            "key_id": f"{args.provider}-key-{len(pool['providers'][args.provider]['keys'])+1:02d}",
            "label": args.label or f"{args.provider} key",
            "env": args.env,
            "status": "standby",
            "activated_at": None,
            "usage": {"last_checked": None, "percentage": None},
        }
        pool["providers"][args.provider]["keys"].append(new_key)
        save_pool(pool)
        print(f"Added {new_key['key_id']} to {args.provider} (standby)")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
