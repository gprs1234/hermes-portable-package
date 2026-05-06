#!/usr/bin/env python3
"""Deterministic Hermes integration report for cron direct delivery."""

import json
import os
from pathlib import Path
from datetime import datetime

HOME = Path.home()
ARENA = Path("<ARENA_ROOT>/arena/arena_control")


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def board_snapshot():
    inbox = load_json(HOME / ".hermes/plan_registry/hermes_inbox.json", [])
    if isinstance(inbox, dict):
        items = inbox.get("items") or inbox.get("messages") or inbox.get("inbox") or []
    elif isinstance(inbox, list):
        items = inbox
    else:
        items = []

    actionable = []
    stale_tests = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("topic") or item.get("subject") or (item.get("payload") or {}).get("title") or ""
        text = " ".join(str(item.get(k, "")) for k in ("topic", "title", "subject", "description", "direction"))
        is_gateway_test = "Gateway v1" in text and ("測試" in text or "驗證" in text)
        row = {
            "event_id": item.get("event_id") or item.get("id"),
            "title": title,
        }
        if is_gateway_test:
            stale_tests.append(row)
        elif item.get("requires_board_vote") is True:
            actionable.append(row)
    return {"actionable": actionable, "stale_tests": stale_tests}


def registry_snapshot():
    registry = load_json(HOME / ".hermes/plan_registry/registry.json", {})
    plans = registry.get("plans", registry if isinstance(registry, dict) else {})
    counts = {}
    for plan in (plans or {}).values():
        if isinstance(plan, dict):
            status = plan.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
    return counts


def active_deficits(report):
    deficits = []
    for issue in report.get("issues") or []:
        if (issue.get("issue_id") or issue.get("id")) != "ACTIVE_STRATEGY_COUNT_LOW":
            continue
        details = issue.get("details") or {}
        module = details.get("module") or issue.get("module") or issue.get("component") or "unknown"
        active = details.get("active_strategies")
        if active is None:
            active = issue.get("active_count")
        target = details.get("target_strategies") or issue.get("target_count") or 100
        deficit = details.get("deficit")
        if deficit is None:
            deficit = issue.get("need")
        if deficit is None and isinstance(active, int):
            deficit = max(0, int(target) - active)
        deficits.append({"module": module, "active": active, "target": target, "deficit": deficit or 0})
    return deficits


def replenishment_status():
    req = load_json(ARENA / "replenishment_requests.json", {})
    if not isinstance(req, dict):
        return {}
    raw_requests = req.get("requests")
    if raw_requests is None and isinstance(req.get("modules"), dict):
        raw_requests = list(req["modules"].values())
    requests = raw_requests or []
    total_needed = 0
    modules = []
    for item in requests:
        if not isinstance(item, dict):
            continue
        need = item.get("needed") or item.get("count") or item.get("need") or item.get("total") or 0
        try:
            need = int(need)
        except Exception:
            need = 0
        total_needed += need
        modules.append(f"{item.get('module', 'unknown')} 缺 {need}")
    return {
        "status": req.get("status"),
        "generated_by": req.get("generated_by"),
        "total_needed": total_needed,
        "modules": modules,
    }


def arena_report():
    report = load_json(ARENA / "plan_agent_report.json", {})
    if not isinstance(report, dict):
        return None
    summary = report.get("summary") or {}
    services = {}
    for item in report.get("services") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        services[item["name"]] = item.get("running")
    return {
        "generated_at": report.get("generated_at"),
        "summary": summary,
        "services": services,
        "deficits": active_deficits(report),
        "replenishment": replenishment_status(),
    }


def missing_model_env(deficits):
    module_to_keys = {
        "gpt_5.5": ("ARENA_BANANA_API_KEY", "ARENA_BANANA_BASE_URL"),
        "opus_4.6": ("ARENA_CDNI_API_KEY", "ARENA_CDNI_BASE_URL"),
        "opus_4.7": ("ARENA_CDNI_API_KEY", "ARENA_CDNI_BASE_URL"),
        "deepseek_v4_pro": ("ARENA_DEEPSEEK_API_KEY", "ARENA_DEEPSEEK_BASE_URL"),
        "mimo-v2-pro": ("ARENA_MIMO_API_KEY", "ARENA_MIMO_BASE_URL"),
    }
    env_text = ""
    for path in (HOME / "projects/.env", HOME / ".hermes/.env"):
        try:
            env_text += "\n" + path.read_text(encoding="utf-8")
        except Exception:
            pass
    missing = set()
    for d in deficits:
        for key in module_to_keys.get(d["module"], ()):
            if f"{key}=" not in env_text:
                missing.add(key)
    return sorted(missing)


def main():
    arena = arena_report()
    board = board_snapshot()
    registry = registry_snapshot()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not arena:
        print("🏛️ Hermes 整合報告\n━━━━━━━━━━━━\n🔴 無法讀取競技場報告資料\n━━━━━━━━━━━━\n需要你: 需要檢查 arena_control/plan_agent_report.json")
        return

    summary = arena["summary"]
    deficits = arena["deficits"]
    total_deficit = sum(int(d.get("deficit") or 0) for d in deficits)
    high_or_critical = int(summary.get("critical_issues") or 0) + int(summary.get("high_issues") or 0)
    actionable = board["actionable"]
    should_report = bool(high_or_critical or actionable or total_deficit)

    if not should_report:
        print("[SILENT]")
        print(json.dumps({"wakeAgent": False}, ensure_ascii=False))
        return

    lines = [
        "🏛️ Hermes 整合報告",
        "━━━━━━━━━━━━",
        f"🕐 巡邏時間：{now}",
        "",
        f"🟠 競技場：{summary.get('status', 'UNKNOWN')}（健康分數 {summary.get('health_score', 'N/A')}）",
    ]

    services = arena["services"]
    running = [k for k, v in services.items() if v is True]
    down = [k for k, v in services.items() if v is False]
    if down:
        lines.append(f"🔴 服務異常：{', '.join(down)}")
    if running:
        lines.append(f"✅ 服務運行：{', '.join(running)}")

    if deficits:
        lines.append("")
        lines.append(f"⚠️ 策略補位缺口：共缺 {total_deficit} 個 active 策略")
        for item in deficits:
            lines.append(f"- {item['module']}: {item['active']}/{item['target']}，缺 {item['deficit']}")

    repl = arena["replenishment"]
    if repl:
        lines.append("")
        lines.append(f"📌 補位請求：{repl.get('status') or 'unknown'}，總需求 {repl.get('total_needed', 0)}")
        if repl.get("generated_by"):
            lines.append(f"- 來源：{repl['generated_by']}")

    missing = missing_model_env(deficits)
    if missing:
        lines.append("")
        lines.append("🟡 為什麼還沒自動補上：競技場模型 API env 尚未完整設定")
        lines.append("- 缺少：" + ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else ""))
        lines.append("- Hermes 不能偽造其他模型策略，所以目前只能 truthful pending，不能假裝健康。")

    if actionable:
        lines.append("")
        lines.append(f"📋 董事會：{len(actionable)} 項待處理")
        for item in actionable[:5]:
            lines.append(f"- {item.get('event_id')}: {item.get('title') or '未命名'}")
    elif board["stale_tests"]:
        lines.append("")
        lines.append(f"📋 董事會：0 項 actionable（{len(board['stale_tests'])} 項 Gateway v1 測試保留為 audit，不需投票）")

    lines.append("")
    lines.append(f"📊 PLAN：{sum(registry.values())} 個（" + ", ".join(f"{k} {v}" for k, v in sorted(registry.items())) + "）")
    lines.append("━━━━━━━━━━━━")
    # Check if any arena env vars are actually missing
    missing_env = missing_model_env(deficits)
    if missing_env:
        lines.append(f"需要你: 補齊競技場模型 API env: {', '.join(missing_env)}")
    elif total_deficit > 0:
        lines.append("需要你: 暫不需要手動操作；generator 可自動補位。")
    else:
        lines.append("需要你: 暫不需要手動操作。")
    report = "\n".join(lines)
    if os.environ.get("HERMES_INTEGRATION_REPORT_SEND", "1") != "0":
        try:
            import tg_notify
            ok = tg_notify.send(report)
            print("TG_SEND: sent" if ok else "TG_SEND: failed")
        except Exception as exc:
            print(f"TG_SEND: failed ({type(exc).__name__})")
    print(report)
    # Existing cron scheduler reads only the last non-empty line for wake-gate.
    # This prevents a second LLM-based pass and avoids leaking 429 errors.
    print(json.dumps({"wakeAgent": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
