#!/usr/bin/env python3
"""
Governance Dashboard Builder v1.0 (Phase GD1)

產生只讀 Governance Dashboard 報表（markdown + html）。
不開 server，不做任何 action。

Usage:
  python3 governance_dashboard_builder.py
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))

HOME = Path.home()
PROCESS_DIR = HOME / ".hermes" / "process"
GATEWAY_DIR = HOME / ".hermes" / "gateway"
REGISTRY_FILE = HOME / ".hermes" / "plan_registry" / "registry.json"
ACTIVE_CONTEXT = HOME / ".hermes" / "references" / "active_context.md"
EVENTS_LOG = GATEWAY_DIR / "events.jsonl"

MD_OUTPUT = PROCESS_DIR / "governance_dashboard_report.md"
HTML_OUTPUT = PROCESS_DIR / "governance_dashboard.html"


def now_iso():
    return datetime.now(TZ).isoformat()


def safe_read(path):
    """安全讀取，不存在就回 None"""
    p = Path(path)
    if p.exists():
        try:
            return p.read_text()
        except:
            return None
    return None


def safe_read_json(path):
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except:
            return None
    return None


def redact_paths(text):
    """紅遮本地路徑"""
    if not text:
        return text
    text = re.sub(r"/home/\S+", "~", text)
    return text


# ── 資料收集 ─────────────────────────────────────────────────────

def get_plan_status():
    reg = safe_read_json(REGISTRY_FILE)
    if not reg:
        return []
    plans = []
    for pid, info in reg.get("plans", {}).items():
        plans.append({
            "plan_id": pid,
            "name": info.get("name", "?"),
            "status": info.get("status", "?"),
            "mode": info.get("mode", "—"),
            "source": info.get("source", "?"),
        })
    return sorted(plans, key=lambda x: x["status"])


def get_frozen_modules():
    ac = safe_read(ACTIVE_CONTEXT) or ""
    modules = []
    keywords = {
        "Gateway v1": "Gateway v1",
        "Context Sync": "Context Sync",
        "Reply Channel": "Reply Channel",
        "Request Intake": "Request Intake",
    }
    for key, label in keywords.items():
        if key in ac:
            if "frozen" in ac or "封版" in ac:
                modules.append({"name": label, "status": "frozen"})
            else:
                modules.append({"name": label, "status": "active"})
    return modules


def get_pending_requests():
    report = safe_read_json(PROCESS_DIR / "tg_request_intake_report_v3.json")
    if not report:
        return {"total": 0, "eligible": 0, "intents": {}}
    return {
        "total": report.get("total_found", 0),
        "eligible": report.get("eligible_for_event", 0),
        "intents": report.get("intent_counts", {}),
        "risks": report.get("risk_counts", {}),
    }


def get_review_state():
    state = safe_read_json(PROCESS_DIR / "tg_request_review_state.json")
    if not state:
        return {"pending": 0, "accepted": 0, "rejected": 0, "clarify": 0}
    reviews = state.get("reviews", {})
    counts = {"pending": 0, "accepted": 0, "rejected": 0, "clarify": 0}
    for r in reviews.values():
        d = r.get("decision", "")
        if d in counts:
            counts[d] += 1
    # Count pending from inbox
    inbox = GATEWAY_DIR / "inbox" / "tg_request"
    if inbox.exists():
        for f in inbox.glob("*.json"):
            try:
                e = json.loads(f.read_text())
                if e.get("event_id") not in reviews:
                    counts["pending"] += 1
            except:
                pass
    return counts


def get_context_sync():
    report = safe_read_json(PROCESS_DIR / "context_update_pending_report.json")
    if not report:
        return {"total": 0, "pending": 0}
    return {
        "total": report.get("total_found", 0),
        "pending": report.get("pending_approval", 0),
    }


def get_reply_state():
    state = safe_read_json(PROCESS_DIR / "tg_reply_approval_state.json")
    if not state:
        return {"approved": 0, "rejected": 0, "sent": 0}
    approvals = state.get("approvals", {})
    counts = {"approved": 0, "rejected": 0, "sent": 0}
    for r in approvals.values():
        s = r.get("status", r.get("decision", ""))
        if s == "sent":
            counts["sent"] += 1
        elif s in counts:
            counts[s] += 1
    return counts


def get_recent_events(limit=10):
    if not EVENTS_LOG.exists():
        return []
    lines = EVENTS_LOG.read_text().strip().split("\n")
    events = []
    for line in lines[-limit:]:
        if line.strip():
            try:
                e = json.loads(line)
                events.append({
                    "time": e.get("created_at", "?")[:19],
                    "type": e.get("event_type", "?"),
                    "source": e.get("source", "?"),
                    "id": e.get("event_id", "?")[:20],
                })
            except:
                continue
    return events


def get_gaps():
    gaps = []
    gap_files = [
        ("TG_CLI_CONTEXT_SYNC_GAP.md", "TG↔CLI Context Sync"),
        ("CLI_TG_REPLY_CHANNEL_GAP.md", "CLI→TG Reply Channel"),
        ("RT3_REPLY_CHANNEL_INCIDENT_20260504.md", "Reply 錯發 Incident"),
    ]
    for fname, label in gap_files:
        f = PROCESS_DIR / fname
        if f.exists():
            content = f.read_text()
            # 找狀態
            if "已修復" in content or "已驗通" in content or "MVP" in content:
                status = "有解法"
            else:
                status = "未解"
            gaps.append({"name": label, "file": fname, "status": status})
    return gaps


def get_up_queue():
    queue_file = PROCESS_DIR / "tg_request_universal_queue.jsonl"
    if not queue_file.exists():
        return {"queued": 0, "analyzed": 0}
    entries = []
    for line in queue_file.read_text().strip().split("\n"):
        if line.strip():
            try:
                entries.append(json.loads(line))
            except:
                continue
    return {
        "queued": sum(1 for e in entries if e.get("status") == "queued"),
        "analyzed": sum(1 for e in entries if e.get("status") == "analyzed"),
    }


# ── 報表產生 ─────────────────────────────────────────────────────

def generate_md():
    now = now_iso()
    plans = get_plan_status()
    frozen = get_frozen_modules()
    requests = get_pending_requests()
    review = get_review_state()
    ctx = get_context_sync()
    reply = get_reply_state()
    events = get_recent_events(10)
    gaps = get_gaps()
    queue = get_up_queue()

    inert_count = sum(1 for p in plans if p["status"] == "inert")
    active_count = sum(1 for p in plans if p["status"] == "active")

    lines = []
    lines.append("# Hermes Governance Dashboard")
    lines.append(f"產生時間: {now}")
    lines.append("")
    # ── Collect trust summary from heartbeats ──────────────────────
    all_heartbeats = {}
    hb_dir = Path.home() / ".hermes" / "plan_registry"
    for hb_file in hb_dir.glob("*_heartbeat.json"):
        hb = safe_read_json(hb_file)
        if hb:
            mid = hb.get("module_id") or hb_file.stem.replace("_heartbeat", "")
            all_heartbeats[mid] = hb
            all_heartbeats[mid.replace("_", "-")] = hb

    # Include selected PLAN factory heartbeat sources that are registered but live outside plan_registry.
    material_hb_file = Path.home() / ".hermes" / "plan_factory" / "plans" / "材料管理" / "heartbeat.json"
    material_hb = safe_read_json(material_hb_file)
    if material_hb:
        all_heartbeats["材料管理"] = material_hb
    trust_counts = {"HEALTHY": 0, "OBSERVED": 0, "SELF_REPORTED": 0, "INERT": 0,
                    "STALE": 0, "GAP": 0, "CRITICAL": 0, "UNKNOWN": 0}
    for hb in all_heartbeats.values():
        s = hb.get("status", "UNKNOWN")
        if s in trust_counts:
            trust_counts[s] += 1
        else:
            trust_counts["UNKNOWN"] += 1

    lines.append("## 1. System Overview")
    lines.append("")
    lines.append("Hermes Mobile Governance Loop v1 MVP")
    lines.append(f"- 七大模組: 全部完成")
    lines.append(f"- 狀態: frozen（觀察期）")
    lines.append(f"- 交易系統: 未接入")
    lines.append(f"- 百大競技場: 未接入")
    lines.append("")
    lines.append("### Health Trust Summary")
    trust_parts = []
    # Break down HEALTHY into verified vs unverified
    healthy_verified = 0
    healthy_unverified = 0
    healthy_missing_meta = 0
    metadata_applied = 0
    for hb in all_heartbeats.values():
        s = hb.get("status", "")
        ext = hb.get("external_verified")
        hs = hb.get("health_source")
        if s == "HEALTHY":
            if ext is True:
                healthy_verified += 1
            elif hs and ext is False:
                healthy_unverified += 1
            else:
                healthy_missing_meta += 1
        if hs and ext is not None and hb.get("trust_level"):
            metadata_applied += 1

    if trust_counts["HEALTHY"] > 0:
        healthy_detail = []
        if healthy_verified > 0: healthy_detail.append(f"verified={healthy_verified}")
        if healthy_unverified > 0: healthy_detail.append(f"unverified={healthy_unverified}")
        if healthy_missing_meta > 0: healthy_detail.append(f"missing_metadata={healthy_missing_meta}")
        trust_parts.append(f"HEALTHY={trust_counts['HEALTHY']} ({', '.join(healthy_detail)})")
    if trust_counts["OBSERVED"] > 0: trust_parts.append(f"OBSERVED={trust_counts['OBSERVED']}")
    if trust_counts["SELF_REPORTED"] > 0: trust_parts.append(f"SELF_REPORTED={trust_counts['SELF_REPORTED']}")
    if trust_counts["INERT"] > 0: trust_parts.append(f"INERT={trust_counts['INERT']}")
    if trust_counts["STALE"] > 0: trust_parts.append(f"STALE={trust_counts['STALE']}")
    if trust_counts["GAP"] > 0: trust_parts.append(f"GAP={trust_counts['GAP']}")
    if trust_counts["CRITICAL"] > 0: trust_parts.append(f"CRITICAL={trust_counts['CRITICAL']}")
    if trust_counts["UNKNOWN"] > 0: trust_parts.append(f"UNKNOWN={trust_counts['UNKNOWN']}")
    lines.append(f"- Heartbeats: {len(all_heartbeats)} total — {', '.join(trust_parts)}")
    lines.append(f"- Metadata applied (HM3): {metadata_applied} / {len(all_heartbeats)}")
    if healthy_missing_meta > 0:
        lines.append(f"- \u26a0\ufe0f HEALTHY with missing metadata: {healthy_missing_meta} (需人工 review)")
    lines.append("")
    # ── Health Trust Legend ────────────────────────────────────────
    lines.append("### Health Trust Legend")
    lines.append("")
    lines.append("| Status | Trust Level | Meaning | Allowed Conclusion | Not Allowed | Next Step |")
    lines.append("|--------|------------|---------|-------------------|-------------|-----------|")
    lines.append("| GAP | none | 無 heartbeat / 無資料 | 未知 | 推斷健康/故障 | 建立 heartbeat 機制 |")
    lines.append("| OBSERVED | passive | 有活動跡象，未外部驗證 | 最近有活動 | 確認健康 / 確認運行中 | external verification |")
    lines.append("| SELF_REPORTED | self | 模組自己回報 | 模組認為自己正常 | 確認健康 | 交叉驗證 |")
    lines.append("| HEALTHY | verified | 外部驗證通過 | 健康 | — | 定期重新驗證 |")
    lines.append("| INERT | declared | 正式存在但未啟動 | 非故障，設計如此 | 推斷為 down | 需要時手動啟動 |")
    lines.append("| STALE | weak_passive | 超過 24h 無活動 | 可能有問題 | 確認故障 | 檢查 bot / 服務 |")
    lines.append("| CRITICAL | anomaly | 明確異常信號 | 有問題 | 忽略 | 立即調查 |")
    lines.append("| UNKNOWN | none | 資料不足 | 未知 | 推斷任何狀態 | 補充資料源 |")
    lines.append("")

    lines.append("## 2. Frozen Modules")
    lines.append("")
    lines.append("| 模組 | 狀態 |")
    lines.append("|------|------|")
    for m in frozen:
        lines.append(f"| {m['name']} | {m['status']} |")
    lines.append(f"| 交易系統 | 未接入 |")
    lines.append(f"| 百大競技場 | 未接入 |")
    lines.append("")
    lines.append("## 3. PLAN Status")
    lines.append("")
    lines.append(f"總計: {len(plans)} 個 PLAN (active: {active_count}, inert: {inert_count})")
    lines.append("")
    lines.append("| PLAN ID | Name | Status | Mode | Trust |")
    lines.append("|---------|------|--------|------|-------|")
    for p in plans:
        emoji = {"active": "🟢", "inert": "⚪", "registered": "🔵"}.get(p["status"], "❓")
        # Trust level from heartbeat
        pid = p["plan_id"]
        hb = all_heartbeats.get(pid, {})
        hb_status = hb.get("status", "")
        if p["status"] == "inert":
            trust = "⬜ INERT (declared)"
        elif hb_status == "HEALTHY":
            hs = hb.get("health_source")
            ext = hb.get("external_verified")
            if hs and ext is True:
                trust = "🟢 HEALTHY (external verified)"
            elif hs and ext is False:
                trust = "🟡 HEALTHY (not external verified)"
            else:
                trust = "⚠️ HEALTHY (missing metadata)"
        elif hb_status == "OBSERVED":
            trust = "🟡 OBSERVED (passive)"
        elif hb_status == "SELF_REPORTED":
            trust = "🔵 SELF_REPORTED"
        elif hb_status == "CRITICAL":
            trust = "🔴 CRITICAL (anomaly)"
        elif hb_status == "STALE":
            trust = "🟠 STALE (weak)"
        elif hb_status == "GAP":
            trust = "⬛ GAP (none)"
        elif hb_status == "not_started":
            trust = "⬛ NOT_STARTED (template)"
        elif hb_status == "UNKNOWN":
            trust = "❓ UNKNOWN"
        elif p["status"] == "active":
            trust = "🔵 active (no heartbeat)"
        else:
            trust = "— (no heartbeat)"
        lines.append(f"| {pid} | {p['name']} | {emoji} {p['status']} | {p['mode']} | {trust} |")
    lines.append("")
    lines.append("## 4. Pending TG Requests")
    lines.append("")
    lines.append(f"- 掃描到: {requests['total']} 筆")
    lines.append(f"- eligible: {requests['eligible']} 筆")
    lines.append(f"- Review: pending={review['pending']}, accepted={review['accepted']}, rejected={review['rejected']}, clarify={review['clarify']}")
    lines.append(f"- UP Queue: queued={queue['queued']}, analyzed={queue['analyzed']}")
    lines.append("")
    lines.append("## 5. Pending Context Updates")
    lines.append("")
    lines.append(f"- 掃描到: {ctx['total']} 筆")
    lines.append(f"- 待審核: {ctx['pending']} 筆")
    lines.append("")
    lines.append("## 6. Pending TG Replies")
    lines.append("")
    lines.append(f"- 已發送: {reply['sent']}")
    lines.append(f"- 已批准: {reply['approved']}")
    lines.append(f"- 已拒絕: {reply['rejected']}")
    lines.append("")
    lines.append("## 7. Recent Events (last 10)")
    lines.append("")
    lines.append("| 時間 | 類型 | 來源 | ID |")
    lines.append("|------|------|------|-----|")
    for e in events:
        lines.append(f"| {e['time']} | {e['type']} | {e['source']} | {e['id']} |")
    lines.append("")
    lines.append("## 8. Known Gaps")
    lines.append("")
    lines.append("| Gap | 狀態 |")
    lines.append("|-----|------|")
    for g in gaps:
        emoji = "✅" if g["status"] == "有解法" else "❌"
        lines.append(f"| {g['name']} | {emoji} {g['status']} |")
    lines.append("")
    # ── GD2: Action Checklist ───────────────────────────────────────
    actions = build_action_checklist(plans, review, queue, ctx, requests)

    lines.append("## 9. Action Checklist")
    lines.append("")
    lines.append("| # | Action | Category | Risk | Status | Reason |")
    lines.append("|---|--------|----------|------|--------|--------|")
    for i, a in enumerate(actions, 1):
        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "⛔"}.get(a["risk_level"], "❓")
        status_emoji = {
            "available": "✅",
            "blocked": "🚫",
            "observe": "👁️",
            "needs_approval": "⚠️",
        }.get(a["status"], "❓")
        lines.append(f"| {i} | {a['title']} | {a['category']} | {risk_emoji} {a['risk_level']} | {status_emoji} {a['status']} | {a['reason']} |")
    lines.append("")

    # ── GD2: Suggested Safe Next Actions ──────────────────────────
    safe_actions = [a for a in actions if a["status"] == "available" and a["risk_level"] == "low"]
    safe_actions.sort(key=lambda x: x["recommended_order"])

    lines.append("## 10. Suggested Safe Next Actions")
    lines.append("")
    if safe_actions:
        for i, a in enumerate(safe_actions, 1):
            lines.append(f"{i}. **{a['title']}** — {a['reason']}")
            lines.append(f"   - risk: 🟢 low")
            lines.append(f"   - confirmation: {a['required_confirmation']}")
            lines.append(f"   - related: {', '.join(a['related_files'])}")
    else:
        lines.append("（目前無可用低風險動作）")
    lines.append("")

    # ── GD2: Blocked / Deferred Actions ───────────────────────────
    blocked_actions = [a for a in actions if a["status"] in ("blocked", "observe", "needs_approval")]
    blocked_actions.sort(key=lambda x: {"blocked": 0, "observe": 1, "needs_approval": 2}.get(x["status"], 3))

    lines.append("## 11. Blocked / Deferred Actions")
    lines.append("")
    if blocked_actions:
        for a in blocked_actions:
            status_label = {"blocked": "🚫 BLOCKED", "observe": "👁️ OBSERVE", "needs_approval": "⚠️ NEEDS APPROVAL"}.get(a["status"], a["status"])
            lines.append(f"- **{a['title']}** ({status_label})")
            lines.append(f"  - reason: {a['reason']}")
            lines.append(f"  - risk: {a['risk_level']}")
            lines.append(f"  - confirmation: {a['required_confirmation']}")
    else:
        lines.append("（目前無封鎖動作）")
    lines.append("")

    # ── GD2: Observation Window ───────────────────────────────────
    lines.append("## 12. Observation Window")
    lines.append("")

    frozen_since = "2026-05-04"
    observe_until = "2026-05-07"
    now = datetime.now(timezone(timedelta(hours=8)))
    observe_end = datetime(2026, 5, 7, 23, 59, 59, tzinfo=timezone(timedelta(hours=8)))
    days_remaining = (observe_end - now).days
    in_observation = now < observe_end

    # 檢查是否有 incident
    incident_count = 0
    gap_files = list((Path.home() / ".hermes" / "process").glob("*INCIDENT*"))
    incident_count = len(gap_files)

    lines.append(f"| Module | Frozen Since | Days in Observation |")
    lines.append(f"|--------|-------------|---------------------|")
    lines.append(f"| Gateway v1 | {frozen_since} | {days_remaining}d remaining |")
    lines.append(f"| Context Sync v1 | {frozen_since} | {days_remaining}d remaining |")
    lines.append(f"| Reply Channel v1 | {frozen_since} | {days_remaining}d remaining |")
    lines.append(f"| Request Intake | {frozen_since} | {days_remaining}d remaining |")
    lines.append("")
    lines.append(f"- 觀察期截止: {observe_until}")
    lines.append(f"- 目前狀態: {'🔵 觀察期進行中' if in_observation else '✅ 觀察期已結束'}")
    lines.append(f"- 已知 incidents: {incident_count}")
    lines.append(f"- 建議: {'繼續觀察，不改動模組' if in_observation else '可考慮解凍'}")
    lines.append("")

    # ── GD2: Pending Work Queues ───────────────────────────────────
    lines.append("## 13. Pending Work Queues")
    lines.append("")

    # tg request pending
    tg_pending = review.get("pending", 0)
    # context update review
    ctx_pending = ctx.get("pending", 0)
    # reply pending (approved but not sent)
    reply_approved = reply.get("approved", 0)
    # universal queue
    up_queued = queue.get("queued", 0)
    # plan integration candidates (Candidate A 未接入)
    candidate_a_count = 0
    for p in plans:
        if p["status"] == "inert" and p["plan_id"] != "plan-ff1139da":
            candidate_a_count += 1
    # registered 的也算候選
    for p in plans:
        if p["status"] == "registered" and "test" in p.get("name", "").lower():
            candidate_a_count += 1

    lines.append("| Queue | Pending | Details |")
    lines.append("|-------|---------|---------|")
    lines.append(f"| TG Request Review | {tg_pending} | 待 Owner review 的 TG request |")
    lines.append(f"| Context Update Review | {ctx_pending} | 待審核的 context 更新 |")
    lines.append(f"| Reply Pending | {reply_approved} | 已批准待發送的 reply |")
    lines.append(f"| Universal Queue | {up_queued} | 待分析的通用佇列項目 |")
    lines.append(f"| PLAN Integration Candidates | {candidate_a_count} | 可做 readonly integration 的候選 PLAN |")
    total_pending = tg_pending + ctx_pending + reply_approved + up_queued + candidate_a_count
    lines.append(f"| **Total** | **{total_pending}** | **所有待辦項目總計** |")
    lines.append("")

    # ── GD2: Safety Lock Summary ───────────────────────────────────
    lines.append("## 14. Safety Lock Summary")
    lines.append("")
    lines.append("目前生效的安全鎖：")
    lines.append("")
    lines.append("| Lock | Status | Description |")
    lines.append("|------|--------|-------------|")
    lines.append("| No Trading Integration | 🔒 ACTIVE | trading-server / arena / pos-backend 全部未接入 |")
    lines.append("| No Auto Execution from TG | 🔒 ACTIVE | TG request 必須經過 review + approval 流程 |")
    lines.append("| No Direct active_context Write | 🔒 ACTIVE | context 更新需 Owner approve + apply 兩步確認 |")
    lines.append("| No Service Activation | 🔒 ACTIVE | inert PLAN 不可透過 Dashboard 啟動 |")
    lines.append("| No Board Bypass | 🔒 ACTIVE | 所有決策需經過董事會投票機制 |")
    lines.append("| Final Confirm Required | 🔒 ACTIVE | high/critical 操作需 final_confirm 才執行 |")
    lines.append("| Observation Period Lock | 🔒 ACTIVE | 5/4~5/7 不改動任何 frozen 模組 |")
    lines.append("| Readonly PLAN Integration | 🔒 ACTIVE | 已接入 PLAN 僅限 view_only 操作 |")
    lines.append("")

    lines.append("---")
    lines.append("")

    # ── Section 15: PLAN Detail (readonly_integrated) ──────────────
    integrated_plan_ids = ["plan-ff1139da", "test-formal-demo"]

    registry = safe_read_json(Path.home() / ".hermes" / "plan_registry" / "registry.json")

    for plan_id in integrated_plan_ids:
        plan_dir = Path.home() / ".hermes" / "plans" / plan_id
        if not plan_dir.exists():
            continue

        section_num = 15 + integrated_plan_ids.index(plan_id)
        lines.append(f"## {section_num}. PLAN Detail: {plan_id}")
        lines.append("")
        lines.append("**Integration Status**: readonly_integrated")
        lines.append("**Allowed Actions**: view_only")
        lines.append("**Forbidden Actions**: start / modify / delete / deploy")
        lines.append("")

        # Manifest (read first for name)
        manifest_file = plan_dir / "plan_manifest.json"
        manifest = safe_read_json(manifest_file)
        if manifest:
            lines.append(f"- plan_id: {plan_id}")
            lines.append(f"- name: {manifest.get('plan_name', '?')}")
            lines.append(f"- status: inert")
            lines.append(f"- mode: formal")
            lines.append("")

        # Heartbeat
        hb_file = plan_dir / "heartbeat.json"
        hb = safe_read_json(hb_file)
        if hb:
            lines.append("### Heartbeat")
            lines.append(f"- status: {hb.get('status', '?')}")
            lines.append(f"- active: {hb.get('active', '?')}")
            lines.append(f"- service_started: {hb.get('service_started', '?')}")
            lines.append(f"- auto_start: {hb.get('auto_start', '?')}")
            lines.append(f"- health_score: {hb.get('health_score', '?')}")
            lines.append(f"- last_heartbeat: {str(hb.get('last_heartbeat', '?'))[:19]}")
            if hb.get("issues"):
                lines.append(f"- issues: {', '.join(hb['issues'])}")
            lines.append("")

        # Manifest detail
        if manifest:
            lines.append("### Manifest")
            lines.append(f"- plan_name: {manifest.get('plan_name', '?')}")
            lines.append(f"- build_event_id: {manifest.get('build_event_id', '?')}")
            lines.append(f"- decision_id: {manifest.get('decision_id', '?')}")
            lines.append(f"- correlation_id: {manifest.get('correlation_id', '?')}")
            lines.append(f"- approved_by: {manifest.get('approved_by', '?')}")
            lines.append(f"- built_at: {str(manifest.get('built_at', '?'))[:19]}")
            lines.append(f"- files_created: {len(manifest.get('files_created', []))}")
            lines.append(f"- registry_entry_added: {manifest.get('registry_entry_added', '?')}")
            lines.append("")

        # Files present
        lines.append("### Files Present")
        if plan_dir.exists():
            for f in sorted(plan_dir.rglob("*")):
                if f.is_file():
                    size = f.stat().st_size
                    rel = f.relative_to(plan_dir)
                    lines.append(f"- {rel} ({size} bytes)")
        lines.append("")

        # Reports / Logs count
        reports_dir = plan_dir / "reports"
        logs_dir = plan_dir / "logs"
        reports_count = len(list(reports_dir.glob("*"))) - (1 if (reports_dir / ".keep").exists() else 0) if reports_dir.exists() else 0
        logs_count = len(list(logs_dir.glob("*"))) - (1 if (logs_dir / ".keep").exists() else 0) if logs_dir.exists() else 0
        lines.append(f"### Reports / Logs")
        lines.append(f"- reports: {reports_count} files")
        lines.append(f"- logs: {logs_count} files")
        lines.append("")

        # Registry entry
        if registry:
            reg_entry = registry.get("plans", {}).get(plan_id)
            if reg_entry:
                lines.append("### Registry Entry")
                for k, v in reg_entry.items():
                    lines.append(f"- {k}: {v}")
                lines.append("")

    # ── PI4: PLAN Factory Readonly Card ─────────────────────────────
    factory_plan_id = "材料管理"
    factory_dir = Path.home() / ".hermes" / "plan_factory" / "plans" / factory_plan_id
    if factory_dir.exists():
        lines.append("## 17. PLAN Factory Readonly Card: 材料管理")
        lines.append("")
        lines.append("**Integration Status**: factory_readonly_card")
        lines.append("**Allowed Actions**: view_only")
        lines.append("**Forbidden Actions**: start / modify / delete / deploy / restart / create_bot / write_token / connect_pos")
        lines.append("")

        blueprint = safe_read_json(factory_dir / "blueprint.json")
        hb = safe_read_json(factory_dir / "heartbeat.json")
        skill = safe_read_json(factory_dir / "skill.json")
        registry_entry = registry.get("plans", {}).get(factory_plan_id) if registry else None

        lines.append("### Registry")
        if registry_entry:
            lines.append(f"- plan_id: {registry_entry.get('plan_id', factory_plan_id)}")
            lines.append(f"- name: {registry_entry.get('name', '?')}")
            lines.append(f"- status: {registry_entry.get('status', '?')}")
            lines.append(f"- domain: {registry_entry.get('domain', '?')}")
            lines.append(f"- owner: {registry_entry.get('owner', '?')}")
            lines.append(f"- heartbeat_path: {registry_entry.get('heartbeat', {}).get('path', '?')}")
        else:
            lines.append("- registry entry: missing")
        lines.append("")

        if blueprint:
            lines.append("### Blueprint")
            lines.append(f"- description: {blueprint.get('description', '?')}")
            lines.append(f"- data_layer: {blueprint.get('data_layer', {}).get('type', '?')}")
            integrations = blueprint.get('data_layer', {}).get('integrations', [])
            lines.append(f"- planned_integrations: {', '.join(integrations) if integrations else 'none'}")
            stack = blueprint.get('tech_stack', {})
            lines.append(f"- language: {stack.get('language', '?')}")
            framework = stack.get('framework', {})
            lines.append(f"- framework_api: {framework.get('api', '?')}")
            lines.append(f"- external_actions_require_human: {len(blueprint.get('external_actions', []))}")
            lines.append("")

        if hb:
            lines.append("### Heartbeat")
            lines.append(f"- status: {hb.get('status', '?')}")
            lines.append(f"- source: {hb.get('source', '?')}")
            lines.append(f"- pid: {hb.get('pid', '?')}")
            lines.append(f"- score: {hb.get('score', '?')}")
            lines.append(f"- timestamp: {str(hb.get('timestamp', '?'))[:19]}")
            lines.append("")

        lines.append("### Files Present")
        for f in sorted(factory_dir.iterdir()):
            if f.is_file():
                lines.append(f"- {f.name} ({f.stat().st_size} bytes)")
        lines.append("")

        if skill:
            lines.append("### Skill Declaration")
            lines.append(f"- skill_name: {skill.get('name', '?')}")
            lines.append(f"- version: {skill.get('version', '?')}")
            lines.append(f"- triggers: {len(skill.get('triggers', []))}")
            lines.append(f"- actions_declared: {len(skill.get('actions', []))}")
            lines.append("- note: skill actions are displayed only; Dashboard must not execute restart/check commands.")
            lines.append("")

        lines.append("### Safety Notes")
        lines.append("- 此卡只代表已能被治理 dashboard 看見，不代表 PLAN 已啟動。")
        lines.append("- status=not_started，不是 active service。")
        lines.append("- planned POS integration 仍未接入，任何 POS/金錢相關動作都 blocked。")
        lines.append("- Telegram bot token / BotFather / .env 均未處理。")
        lines.append("")
    # ── CI2: Core Infrastructure Status ─────────────────────────────
    registry = safe_read_json(Path.home() / ".hermes" / "plan_registry" / "registry.json")

    lines.append("")
    lines.append("## 18. Core Infrastructure Status")
    lines.append("")
    lines.append("核心基礎設施模組 — 不適用一般 PLAN Detail，獨立顯示。")
    lines.append("")

    # hermes-tg-bot core card
    if registry:
        bot_reg = registry.get("plans", {}).get("hermes-tg-bot", {})
        bot_meta = bot_reg.get("metadata", {})
        bot_stats = bot_reg.get("stats", {})
        bot_hb = bot_reg.get("heartbeat", {})

        lines.append("### hermes-tg-bot (tg_interface)")
        lines.append("")
        lines.append(f"- module_id: hermes-tg-bot")
        lines.append(f"- name: {bot_reg.get('name', '?')}")
        lines.append(f"- role: tg_interface — Owner 的對話窗口")
        lines.append(f"- description: {bot_reg.get('description', '?')}")
        lines.append(f"- status: {bot_reg.get('status', '?')}")
        lines.append(f"- domain: {bot_reg.get('domain', '?')}")
        lines.append(f"- owner: {bot_reg.get('owner', '?')}")
        lines.append(f"- criticality: {bot_meta.get('critical_level', '?')}")
        lines.append("")
        # Read passive heartbeat if available
        hb_file = Path.home() / ".hermes" / "plan_registry" / "hermes_tg_bot_heartbeat.json"
        passive_hb = safe_read_json(hb_file)

        lines.append("#### Health")
        if passive_hb:
            hb_status = passive_hb.get("status", "UNKNOWN")
            hb_source = passive_hb.get("health_source", "unknown")
            hb_ext = passive_hb.get("external_verified", False)
            hb_ts = str(passive_hb.get("timestamp", ""))[:19]
            hb_confidence = passive_hb.get("confidence", "unknown")
            hb_polling = passive_hb.get("polling_alive", "unknown")
            hb_reply_ch = passive_hb.get("reply_channel_alive", "unknown")
            hb_ctx = passive_hb.get("context_sync_alive", "unknown")

            lines.append(f"- health_source: {hb_source} — {'external verified' if hb_ext else 'NOT external verified'}")
            lines.append(f"- self_monitoring_risk: false（介面層，不監控自己）")
            # Trust level derivation
            trust_map = {
                "GAP": "none",
                "OBSERVED": "passive",
                "SELF_REPORTED": "self",
                "HEALTHY": "verified",
                "STALE": "weak_passive",
                "UNKNOWN": "none",
            }
            trust_level = trust_map.get(hb_status, "unknown")

            lines.append(f"- heartbeat_status: {hb_status}")
            lines.append(f"- trust_level: {trust_level}")
            if not hb_ext:
                lines.append(f"- ⚠️ NOT external verified — status is NOT HEALTHY")
            lines.append(f"- heartbeat_confidence: {hb_confidence}")
            lines.append(f"- last_heartbeat: {hb_ts}")
            lines.append(f"- polling_alive: {hb_polling}")
            lines.append(f"- reply_channel_alive: {hb_reply_ch}")
            lines.append(f"- context_sync_alive: {hb_ctx}")
            lines.append(f"- last_chat_history: {str(passive_hb.get('last_chat_history_at', 'none'))[:19]}")
            lines.append(f"- last_reply_sent: {str(passive_hb.get('last_reply_sent_at', 'none'))[:19]}")
            lines.append(f"- last_request: {str(passive_hb.get('last_request_ingested_at', 'none'))[:19]}")
            lines.append(f"- last_context_sync: {str(passive_hb.get('last_context_sync_at', 'none'))[:19]}")
            if passive_hb.get("issues"):
                for issue in passive_hb["issues"]:
                    lines.append(f"- ⚠️ {issue}")
        else:
            lines.append(f"- health_source: registry only — NOT external verified")
            lines.append(f"- self_monitoring_risk: false（介面層，不監控自己）")
            lines.append(f"- heartbeat_status: GAP (no heartbeat file)")
            lines.append(f"- heartbeat_path: {bot_hb.get('path', 'N/A')}")
        lines.append("")
        lines.append("#### Dependencies")
        lines.append(f"- dependency_direction: outbound（依賴外部，無模組依賴它）")
        lines.append(f"- depends_on: hermes-gateway, telegram bot token, chat_id")
        lines.append(f"- location: {bot_meta.get('location', '?')}")
        lines.append(f"- process: {bot_meta.get('process', '?')}")
        lines.append(f"- gateway_bot: {bot_meta.get('gateway_bot', '?')}")
        lines.append(f"- auto_restart: {bot_meta.get('auto_restart', '?')}")
        lines.append("")
        lines.append("#### Actions")
        lines.append(f"- integration_status: core_readonly_card")
        lines.append(f"- allowed_actions: view_only")
        lines.append(f"- forbidden_actions: start / modify / delete / restart / self_approve / send_message")
        lines.append(f"- manual_review_required: true")
        lines.append("")
        lines.append("#### Activity Summary（from Governance Loop）")
        # Reply channel
        reply_state = safe_read_json(PROCESS_DIR / "tg_reply_approval_state.json")
        if reply_state:
            approvals = reply_state.get("approvals", {})
            r_counts = {"approved": 0, "rejected": 0, "sent": 0}
            for r in approvals.values():
                s = r.get("status", r.get("decision", ""))
                if s == "sent":
                    r_counts["sent"] += 1
                elif s in r_counts:
                    r_counts[s] += 1
            lines.append(f"- reply_sent: {r_counts['sent']}")
            lines.append(f"- reply_approved: {r_counts['approved']}")
            lines.append(f"- reply_rejected: {r_counts['rejected']}")
        # Request intake
        req_report = safe_read_json(PROCESS_DIR / "tg_request_intake_report_v3.json")
        if req_report:
            lines.append(f"- requests_total: {req_report.get('total_found', 0)}")
            lines.append(f"- requests_eligible: {req_report.get('eligible_for_event', 0)}")
        lines.append("")

    # ── GD4: Health Source Audit / Metadata Incomplete ─────────────
    audit_report = safe_read_json(PROCESS_DIR / "health_source_audit_report.json")
    lines.append("## 19. Health Source Audit / Metadata Incomplete")
    lines.append("")
    lines.append("Heartbeat metadata 可信度檢查。此區塊只讀，不修復、不重啟、不改 status。")
    lines.append("")

    if audit_report:
        lines.append("### Audit Summary")
        lines.append(f"- total_heartbeats: {audit_report.get('total', 0)}")
        lines.append(f"- missing_health_source: {audit_report.get('missing_health_source', 0)}")
        lines.append(f"- not_external_verified: {audit_report.get('not_external_verified', 0)}")
        lines.append(f"- stale_timestamp: {audit_report.get('stale_timestamp', 0)}")
        lines.append(f"- needs_review: {audit_report.get('needs_review', 0)}")
        lines.append("")

        # GD4: Metadata Completeness Score
        METADATA_FIELDS = ["health_source", "confidence", "trust_level", "external_verified"]
        lines.append("### Metadata Completeness Score (GD4)")
        lines.append("")
        lines.append("每個 heartbeat 的 4 個關鍵 metadata 欄位填寫狀態。")
        lines.append("")
        lines.append("| Plan ID | Status | health_source | confidence | trust_level | ext_verified | Score |")
        lines.append("|---------|--------|---------------|------------|-------------|--------------|-------|")

        score_dist = {"4/4": [], "3/4": [], "0/4": []}
        for hb in audit_report.get("heartbeats", []):
            pid = hb.get("plan_id", "?")
            status = hb.get("status", "?")
            hs = "✅" if hb.get("health_source") else "❌"
            conf = "✅" if hb.get("confidence") else "❌"
            tl = "✅" if hb.get("trust_level") else "❌"
            ev = "✅" if hb.get("external_verified") is not None and hb.get("external_verified") is True else ("⚠️" if hb.get("external_verified") is not None else "❌")
            filled = sum([
                1 if hb.get("health_source") else 0,
                1 if hb.get("confidence") else 0,
                1 if hb.get("trust_level") else 0,
                1 if hb.get("external_verified") is not None else 0,
            ])
            score = f"{filled}/4"
            lines.append(f"| {pid} | {status} | {hs} | {conf} | {tl} | {ev} | {score} |")
            bucket = score if score in score_dist else "0/4"
            score_dist[bucket].append(pid)

        lines.append("")
        lines.append("### Completeness Distribution")
        for score, pids in sorted(score_dist.items(), reverse=True):
            if pids:
                lines.append(f"- {score}: {', '.join(pids)} ({len(pids)})")
        lines.append("")

        # Archived plans note
        lines.append("### Archived Plans")
        lines.append("- 材料管理: archived (never started, watchdog skip enabled)")
        lines.append("")

        incomplete = []
        passive = []
        critical = []
        for hb in audit_report.get("heartbeats", []):
            issues = hb.get("trust_issues", []) or []
            if hb.get("health_source") is None or "missing_health_source" in issues or "not_external_verified" in issues:
                incomplete.append(hb)
            elif "passive_only" in issues:
                passive.append(hb)
            if hb.get("status") == "CRITICAL":
                critical.append(hb)

        lines.append("### Metadata Incomplete")
        if incomplete:
            lines.append("| Plan ID | Status | Missing / Issue | Risk Handling | Recommended Action |")
            lines.append("|---------|--------|-----------------|---------------|--------------------|")
            for hb in incomplete:
                issues = ", ".join(hb.get("trust_issues", []) or ["metadata_incomplete"])
                pid = hb.get("plan_id", "?")
                status = hb.get("status", "?")
                if pid in ["trading-server"]:
                    handling = "blocked — trading related"
                elif pid in ["board-bot", "watchdog"]:
                    handling = "manual review — core infrastructure"
                else:
                    handling = "manual review"
                action = hb.get("recommended_action", "review")
                lines.append(f"| {pid} | {status} | {issues} | {handling} | {action} |")
        else:
            lines.append("- 無 metadata incomplete heartbeat。")
        lines.append("")

        lines.append("### Passive / Not External Verified")
        if passive:
            lines.append("| Plan ID | Status | Source | Trust | Recommended Action |")
            lines.append("|---------|--------|--------|-------|--------------------|")
            for hb in passive:
                lines.append(f"| {hb.get('plan_id', '?')} | {hb.get('status', '?')} | {hb.get('health_source', '?')} | {hb.get('trust_level', '?')} | {hb.get('recommended_action', 'review')} |")
        else:
            lines.append("- 無 passive-only heartbeat。")
        lines.append("")

        lines.append("### Critical Signals")
        if critical:
            lines.append("| Plan ID | Status | Source | External Verified | Meaning |")
            lines.append("|---------|--------|--------|-------------------|---------|")
            for hb in critical:
                source = hb.get("health_source", "?")
                ext = hb.get("external_verified", "?")
                meaning = "critical remains critical; source labels context only"
                lines.append(f"| {hb.get('plan_id', '?')} | {hb.get('status', '?')} | {source} | {ext} | {meaning} |")
        else:
            lines.append("- 無 CRITICAL heartbeat。")
        lines.append("")

        lines.append("### Safety Notes")
        lines.append("- Dashboard 不得把 CRITICAL 轉成 HEALTHY。")
        lines.append("- Dashboard 不得自動 patch board-bot / watchdog / trading-server。")
        lines.append("- trading-server 仍 blocked，任何交易相關操作需董事會 + Owner final_confirm。")
        lines.append("- mt4_ea 的 manual_observed 只代表 CRITICAL 有人工接受的上下文，不代表修復。")
    else:
        lines.append("- health_source_audit_report.json 不存在或不可讀。")
    lines.append("")

    # ── GD5: Automation Candidate Queues ───────────────────────────
    lines.append("## 20. Automation Candidate Queues")
    lines.append("")
    lines.append("顯示 RI4B / RT4B 的候選狀態。此區塊只讀，不建立事件、不發送 Telegram。")
    lines.append("")

    ri4b = safe_read_json(PROCESS_DIR / "tg_request_result_eligibility_report.json")
    rt4b = safe_read_json(PROCESS_DIR / "tg_reply_retry_preview_report.json")

    lines.append("### RI4B Result-to-Reply Eligibility")
    if ri4b:
        lines.append(f"- queue_items: {ri4b.get('total_queue_items', 0)}")
        lines.append(f"- eligible_candidates: {ri4b.get('eligible_candidates', 0)}")
        lines.append(f"- ineligible_items: {ri4b.get('ineligible_items', 0)}")
        lines.append(f"- reply_events_created: {ri4b.get('reply_events_created', 0)}")
        lines.append(f"- telegram_sent: {str(ri4b.get('telegram_sent', False)).lower()}")
        for item in ri4b.get("items", []):
            reasons = ", ".join(item.get("reasons", [])) if item.get("reasons") else "none"
            lines.append(f"- {item.get('request_id')}: eligible={item.get('eligible')} reason={reasons}")
    else:
        lines.append("- RI4B report missing")
    lines.append("")

    lines.append("### RT4B Reply Retry Preview")
    if rt4b:
        lines.append(f"- reply_events_scanned: {rt4b.get('reply_events_scanned', 0)}")
        lines.append(f"- eligible_retry_previews: {rt4b.get('eligible_retry_previews', 0)}")
        lines.append(f"- retry_previews_created: {rt4b.get('retry_previews_created', 0)}")
        lines.append(f"- telegram_sent: {str(rt4b.get('telegram_sent', False)).lower()}")
        for item in rt4b.get("items", []):
            reasons = ", ".join(item.get("reasons", [])) if item.get("reasons") else "none"
            lines.append(f"- {item.get('reply_event_id')}: eligible={item.get('eligible_for_retry_preview')} reason={reasons}")
    else:
        lines.append("- RT4B report missing")
    lines.append("")

    lines.append("### Safety Notes")
    lines.append("- RI4B 不得直接建立 tg.reply.requested event。")
    lines.append("- RT4B 不得 retry sent event。")
    lines.append("- 任何 candidate 仍需 Reply Channel v1 approve_send + preflight + send_confirm。")
    lines.append("")

    # ── GD6: TG Desktop E2E Validation ─────────────────────────────
    lines.append("## 21. TG Desktop Agent E2E Validation")
    lines.append("")
    e2e = safe_read_json(PROCESS_DIR / "tg_desktop_e2e_validation_report.json")
    if e2e:
        lines.append(f"- generated_at: {e2e.get('generated_at', '?')}")
        lines.append(f"- result: {e2e.get('passed', 0)} / {e2e.get('total', 0)} checks passed")
        lines.append(f"- mode: {e2e.get('mode', '?')}")
        lines.append(f"- telegram_sent_by_validator: {str(e2e.get('telegram_sent', False)).lower()}")
        lines.append(f"- services_started: {str(e2e.get('services_started', False)).lower()}")
        lines.append(f"- trading_touched: {str(e2e.get('trading_touched', False)).lower()}")
        lines.append("")
        lines.append("### Checks")
        lines.append("| Check | Pass | Notes |")
        lines.append("|-------|------|-------|")
        for name, result in e2e.get("checks", {}).items():
            notes = []
            for key in ["pending_approval", "eligible", "reviews", "queue_lines", "sent_count", "sent_to_myhermes", "missing_health_source", "message_count"]:
                if key in result:
                    notes.append(f"{key}={result[key]}")
            if result.get("missing"):
                notes.append("missing=" + ",".join(result.get("missing", [])))
            lines.append(f"| {name} | {result.get('pass')} | {'; '.join(notes) if notes else 'ok'} |")
    else:
        lines.append("- E2E validation report missing")
    lines.append("")
    lines.append("### Live Test Note")
    lines.append("- CLI→TG outbound 已有實際 sent event。")
    lines.append("- 新鮮 TG→CLI inbound 仍需要 Owner 從 TG 發一則真人訊息，因為 agent 無法替人類製造 inbound user message。")
    lines.append("")

    # ── PI4: ai-dashboard Readonly Integration ─────────────────────
    lines.append("## 22. PLAN Detail: ai-dashboard (Readonly Integrated)")
    lines.append("")
    ai_dash = registry.get("plans", {}).get("ai-dashboard", {})
    ai_hb = safe_read_json(HOME / ".hermes" / "plan_registry" / "ai_dashboard_heartbeat.json")
    lines.append(f"- plan_id: ai-dashboard")
    lines.append(f"- name: {ai_dash.get('name', 'AI Visualization Dashboard')}")
    lines.append(f"- domain: {ai_dash.get('domain', 'visualization')}")
    lines.append(f"- status: {ai_dash.get('status', '?')}")
    lines.append(f"- integration: readonly_integrated (PI4)")
    lines.append(f"- allowed_actions: view_only")
    lines.append(f"- forbidden_actions: start / modify / delete / deploy / restart")
    lines.append("")
    if ai_hb:
        lines.append("### Heartbeat")
        lines.append(f"- service: {ai_hb.get('service', '?')}")
        lines.append(f"- type: {ai_hb.get('type', '?')}")
        lines.append(f"- status: {ai_hb.get('status', '?')}")
        lines.append(f"- message: {ai_hb.get('message', '?')}")
        details = ai_hb.get("details", {})
        for check in details.get("checks", []):
            lines.append(f"- check {check.get('check', '?')}: {check.get('status', '?')}")
    else:
        lines.append("- Heartbeat: not available")
    lines.append("")
    lines.append("### Safety")
    lines.append("- 只讀整合，未修改 PLAN")
    lines.append("- 未修改 registry")
    lines.append("- 未啟動/停止服務")
    lines.append("- Flask app.py 狀態由 heartbeat 回報")
    lines.append("")

    # ── CI3: Extended Core Infrastructure Cards ──────────────────
    lines.append("## 23. Core Infrastructure: Gateway / Board-Bot / Watchdog")
    lines.append("")
    lines.append("核心基礎設施擴充卡片 — hermes-tg-bot 已在 Section 18。")
    lines.append("")

    core_modules = [
        ("hermes-gateway", "Hermes Gateway", "gateway — CLI↔董事會↔TG 事件路由核心", "MAXIMUM"),
        ("board-bot", "Board Bot", "ai-company — 董事會決議引擎", "HIGH"),
        ("watchdog", "Watchdog", "ai-company — 全域監控看門狗", "HIGH"),
    ]

    for pid, name, role, criticality in core_modules:
        plan = registry.get("plans", {}).get(pid, {})
        hb_path = HOME / ".hermes" / "plan_registry" / f"{pid.replace('-', '_')}_heartbeat.json"
        hb = safe_read_json(hb_path)
        lines.append(f"### {name} ({pid})")
        lines.append(f"- role: {role}")
        lines.append(f"- criticality: {criticality}")
        lines.append(f"- registry_status: {plan.get('status', '?')}")
        lines.append(f"- domain: {plan.get('domain', '?')}")
        if hb:
            lines.append(f"- heartbeat_status: {hb.get('status', '?')}")
            lines.append(f"- last_heartbeat: {hb.get('timestamp', '?')}")
        lines.append(f"- integration: core_readonly (CI3)")
        lines.append(f"- allowed_actions: view_only")
        lines.append(f"- forbidden_actions: start / modify / delete / deploy / restart")
        lines.append("")

    # ── PI5 + PI6: Additional PLAN Readonly Integrations ─────────
    extra_plans = [
        ("pos-backend", "POS Backend (Cloudflare Worker)", "pos — Cloudflare Worker API", 24),
        ("keyword-image-gen", "Keyword Image Generator", "creative — AI 圖片生成", 25),
    ]

    for pid, name, desc, section_num in extra_plans:
        plan = registry.get("plans", {}).get(pid, {})
        hb = safe_read_json(HOME / ".hermes" / "plan_registry" / f"{pid.replace('-', '_')}_heartbeat.json")
        lines.append(f"## {section_num}. PLAN Detail: {pid} (Readonly Integrated)")
        lines.append("")
        lines.append(f"- plan_id: {pid}")
        lines.append(f"- name: {name}")
        lines.append(f"- description: {desc}")
        lines.append(f"- status: {plan.get('status', '?')}")
        lines.append(f"- domain: {plan.get('domain', '?')}")
        lines.append(f"- integration: readonly_integrated (PI{section_num - 19})")
        lines.append(f"- allowed_actions: view_only")
        lines.append(f"- forbidden_actions: start / modify / delete / deploy / restart")
        if hb:
            lines.append(f"- heartbeat_status: {hb.get('status', '?')}")
            lines.append(f"- heartbeat_message: {hb.get('message', '?')[:80]}")
        lines.append("")
        lines.append(f"### Safety")
        lines.append(f"- 只讀整合，未修改 PLAN / registry / 服務")
        lines.append("")

    # ── AC2: Agent Company OS Sections ────────────────────────────

    # Section 26: Agent Company OS Overview
    lines.append("## 26. Agent Company OS Overview")
    lines.append("")
    lines.append("Hermes 從顧問型 Agent 升級為一人公司作業系統。")
    lines.append("")
    lines.append("- operating_model: Agent Company OS (轉型中)")
    lines.append("- owner: Owner (方向設定 / 最終決策)")
    lines.append("- company_os: Hermes (日常運作 / 自動化)")
    lines.append("- c_level_agents: 7 (CEO, COO, CTO, CFO, CMO, CHRO, CAO)")
    lines.append("- business_units: 1 (arena / 百大交易競技場)")
    lines.append("- concept_cells: 0 (待建立)")
    lines.append("- phase: AC2 — Dashboard + Registry 建立中")
    lines.append("")

    # Section 27: C-Level Agent Roster
    agent_reg = safe_read_json(HOME / ".hermes" / "company" / "agent_registry.json")
    lines.append("## 27. C-Level Agent Roster")
    lines.append("")
    if agent_reg:
        agents = agent_reg.get("agents", {})
        lines.append("| Agent ID | Role | Department | Manager | Mission |")
        lines.append("|----------|------|------------|---------|---------|")
        for aid, agent in agents.items():
            role = agent.get("role_title", "?")
            dept = agent.get("department", "?")
            mgr = agent.get("manager", "?")
            mission = agent.get("mission", "?")[:60]
            lines.append(f"| {aid} | {role} | {dept} | {mgr} | {mission} |")
        lines.append("")
        lines.append("### Authority Summary")
        for aid, agent in agents.items():
            forbidden = ", ".join(agent.get("forbidden", [])[:3])
            lines.append(f"- **{aid}**: forbidden=[{forbidden}]")
        lines.append("")
    else:
        lines.append("- agent_registry.json not found")
        lines.append("")

    # Section 28: Business Unit Operating Map
    bu_reg = safe_read_json(HOME / ".hermes" / "company" / "business_unit_registry.json")
    lines.append("## 28. Business Unit Operating Map")
    lines.append("")
    if bu_reg:
        for bu_id, bu in bu_reg.get("business_units", {}).items():
            lines.append(f"### {bu.get('name', bu_id)} ({bu_id})")
            lines.append(f"- type: {bu.get('type', '?')}")
            lines.append(f"- status: {bu.get('status', '?')}")
            lines.append(f"- lifecycle: {bu.get('lifecycle', '?')}")
            lines.append(f"- owner: {bu.get('owner', '?')}")
            lines.append(f"- primary_c_level: {', '.join(bu.get('primary_c_level', []))}")
            lines.append(f"- process_health: {bu.get('process_health', '?')}")
            lines.append(f"- functional_health: {bu.get('functional_health', '?')}")
            lines.append(f"- user_visible_health: {bu.get('user_visible_health', '?')}")
            lines.append(f"- health_score: {bu.get('health_score', '?')}")
            issues = bu.get("current_issues", [])
            if issues:
                lines.append(f"- current_issues:")
                for issue in issues:
                    lines.append(f"  - {issue}")
            lines.append(f"- next_action: {bu.get('next_action', '?')}")
            lines.append("")
    else:
        lines.append("- business_unit_registry.json not found")
        lines.append("")

    # Section 29: False Health / Functional Health Watch
    lines.append("## 29. False Health / Functional Health Watch")
    lines.append("")
    lines.append("防止 process alive 但 functional degraded 的虛假健康報告。")
    lines.append("")
    if bu_reg:
        bu = bu_reg.get("business_units", {}).get("arena", {})
        lines.append("| Business Unit | Process Health | Functional Health | User-Visible | Deficit | Blocking |")
        lines.append("|---------------|---------------|-------------------|--------------|---------|----------|")
        ph = bu.get("process_health", "?")
        fh = bu.get("functional_health", "?")
        uv = bu.get("user_visible_health", "?")
        deficit = bu.get("active_deficit_total", 0)
        blocking = bu.get("blocking_reason", "none")[:40]
        lines.append(f"| arena | {ph} | {fh} | {uv} | {deficit} | {blocking} |")
        lines.append("")
        lines.append("### False Health Rules")
        lines.append("- 不得報 HEALTHY 如果任何 model < 100 active strategies")
        lines.append("- 不得報 HEALTHY 如果 replenishment pending")
        lines.append("- 不得報 HEALTHY 如果 leaderboard stale")
        lines.append("- functional_health 獨立於 process_health")
        lines.append("- CAO 有權攔截虛假健康報告")
    lines.append("")

    # ── AC5: Operational Patrol Report ──────────────────────────────
    lines.append("## 30. Operational Patrol Report")
    lines.append("")
    patrol_path = HOME / ".hermes" / "process" / "operational_patrol_report.json"
    patrol_data = safe_read_json(patrol_path)
    if patrol_data:
        lines.append(f"- Patrol Time: {patrol_data.get('patrol_at', '?')[:19]}")
        lines.append(f"- BUs Checked: {patrol_data.get('bu_count', 0)}")
        lines.append(f"- Overall: {patrol_data.get('overall_status', '?')}")
        lines.append(f"- False Health Alerts: {len(patrol_data.get('false_health_alerts', []))}")
        lines.append("")
        for result in patrol_data.get("results", []):
            lines.append(f"#### {result.get('bu_name', '?')} ({result.get('bu_id', '?')})")
            lines.append(f"- Process: {result.get('process_health', '?')}")
            lines.append(f"- Functional: {result.get('functional_health', '?')}")
            lines.append(f"- User-Visible: {result.get('user_visible_health', '?')}")
            if result.get("false_health_alert"):
                lines.append("- ⚠️ FALSE HEALTH: process alive but functional degraded!")
            for issue in result.get("issues", []):
                lines.append(f"- Issue: {issue}")
            lines.append("")
    else:
        lines.append("- (no patrol report found — run operational_patrol.py)")
        lines.append("")

    lines.append("")
    # ── Key Usage Dashboard ──────────────────────────────────────
    lines.append("## 31. API Key Usage Dashboard")
    lines.append("")
    key_dash = HOME / ".hermes" / "process" / "key_usage_dashboard.md"
    key_pool_path = HOME / ".hermes" / "key_pool.json"
    key_pool = safe_read_json(key_pool_path)
    if key_pool:
        threshold = key_pool.get("rotation_threshold", 0.95)
        lines.append(f"- Rotation Threshold: {threshold*100:.0f}%")
        lines.append("")
        for prov_name, prov in key_pool.get("providers", {}).items():
            lines.append(f"#### {prov_name}")
            for key in prov.get("keys", []):
                pct = key.get("usage", {}).get("percentage")
                pct_str = f"{pct}%" if pct is not None and pct >= 0 else "?"
                status = key["status"]
                icon = {"active": "🟢", "standby": "⚪", "exhausted": "⚫"}.get(status, "❓")
                lines.append(f"- {icon} {key['key_id']}: {status} | usage={pct_str} | {key.get('label', '')}")
            lines.append("")
        rotation_log = key_pool.get("rotation_log", [])
        if rotation_log:
            last = rotation_log[-1]
            lines.append(f"- Last rotation: {last['timestamp'][:16]} {last['provider']} {last['from_key']} -> {last['to_key']}")
            lines.append("")
    else:
        lines.append("- (no key pool configured)")
        lines.append("")

    lines.append("---")
    lines.append("*Governance Dashboard v3.2 — Company OS + Patrol + Key Pool — 只讀，不執行*")

    return "\n".join(lines)



def build_action_checklist(plans, review, queue, ctx, requests):
    """GD2: 建立 Action Checklist — 動態計算每個動作的可用性"""
    actions = []

    # 收集資料
    inert_plans = [p for p in plans if p["status"] == "inert"]
    registered_plans = [p for p in plans if p["status"] == "registered"]
    active_plans = [p for p in plans if p["status"] == "active"]
    tg_pending = review.get("pending", 0)
    ctx_pending = ctx.get("pending", 0)
    up_queued = queue.get("queued", 0)

    # 已經 readonly integrated 的 PLAN
    integrated_ids = {"plan-ff1139da", "test-formal-demo"}

    # 候選 PLAN（Candidate A 未接入）
    candidate_a_plans = []
    for p in plans:
        pid = p["plan_id"]
        if pid in integrated_ids:
            continue
        if p["status"] in ("inert", "registered"):
            name_lower = p.get("name", "").lower()
            pid_lower = p["plan_id"].lower()
            # 排除交易/金錢相關
            if any(kw in name_lower for kw in ["trading", "交易", "pos", "金錢"]):
                continue
            # 排除核心基礎設施（需 Core Infrastructure Integration Design）
            if any(kw in pid_lower for kw in ["hermes-gateway", "hermes-tg-bot", "watchdog", "board-bot"]):
                continue
            candidate_a_plans.append(p)

    # Action 1: 第二個 readonly PLAN
    if candidate_a_plans:
        best = candidate_a_plans[0]
        actions.append({
            "action_id": "ACT-PI3",
            "title": f"Readonly integrate: {best['plan_id']}",
            "category": "plan_integration",
            "risk_level": "low",
            "status": "available",
            "reason": f"Candidate A PLAN ({best['status']})，score 低",
            "required_confirmation": "none (readonly)",
            "related_files": [f"~/.hermes/plans/{best['plan_id']}/"],
            "recommended_order": 1,
        })
    else:
        actions.append({
            "action_id": "ACT-PI3",
            "title": "Readonly integrate 第二個 PLAN",
            "category": "plan_integration",
            "risk_level": "low",
            "status": "available",
            "reason": "test-formal-demo 可用",
            "required_confirmation": "none (readonly)",
            "related_files": ["~/.hermes/plans/test-formal-demo/"],
            "recommended_order": 1,
        })

    # Action 2: 擴充 dashboard detail
    actions.append({
        "action_id": "ACT-GD3",
        "title": "擴充 Dashboard detail 區塊",
        "category": "dashboard",
        "risk_level": "low",
        "status": "available",
        "reason": "目前只顯示 plan-ff1139da，可擴充更多 PLAN",
        "required_confirmation": "none",
        "related_files": ["~/.hermes/process/governance_dashboard_builder.py"],
        "recommended_order": 2,
    })

    # Action 3: 清理 pending request review
    if tg_pending > 0:
        actions.append({
            "action_id": "ACT-REQ-CLR",
            "title": f"清理 Pending TG Request ({tg_pending} 筆)",
            "category": "request_review",
            "risk_level": "low",
            "status": "available",
            "reason": f"有 {tg_pending} 筆待審核 request",
            "required_confirmation": "逐筆 review",
            "related_files": ["~/.hermes/gateway/inbox/tg_request/"],
            "recommended_order": 3,
        })
    else:
        actions.append({
            "action_id": "ACT-REQ-CLR",
            "title": "清理 Pending TG Request",
            "category": "request_review",
            "risk_level": "low",
            "status": "available",
            "reason": "目前無待審核 request",
            "required_confirmation": "逐筆 review",
            "related_files": ["~/.hermes/gateway/inbox/tg_request/"],
            "recommended_order": 3,
        })

    # Action 4: 整理 SOP 文件
    actions.append({
        "action_id": "ACT-SOP",
        "title": "整理 Governance SOP 文件",
        "category": "documentation",
        "risk_level": "low",
        "status": "available",
        "reason": "process/ 目錄文件可整理為標準化 SOP",
        "required_confirmation": "none",
        "related_files": ["~/.hermes/process/"],
        "recommended_order": 4,
    })

    # Action 5: Readonly health check
    actions.append({
        "action_id": "ACT-RHC",
        "title": "建立 Readonly Health Check",
        "category": "monitoring",
        "risk_level": "low",
        "status": "available",
        "reason": "定時檢查已接入 PLAN 的狀態一致性",
        "required_confirmation": "none",
        "related_files": ["~/.hermes/process/governance_dashboard_builder.py"],
        "recommended_order": 5,
    })

    # Action 6: Modify preview 設計
    actions.append({
        "action_id": "ACT-MPD",
        "title": "設計 Modify Preview 流程",
        "category": "design",
        "risk_level": "low",
        "status": "available",
        "reason": "PI3 前置設計：修改 PLAN 前先 preview diff",
        "required_confirmation": "none (純設計文件)",
        "related_files": ["~/.hermes/process/"],
        "recommended_order": 6,
    })

    # Action 7: 清理 UP queue
    if up_queued > 0:
        actions.append({
            "action_id": "ACT-UP-CLR",
            "title": f"清理 Universal Queue ({up_queued} 筆)",
            "category": "queue_cleanup",
            "risk_level": "low",
            "status": "available",
            "reason": f"有 {up_queued} 筆待分析的通用佇列項目",
            "required_confirmation": "逐筆分析",
            "related_files": ["~/.hermes/process/tg_request_universal_queue.jsonl"],
            "recommended_order": 7,
        })

    # Action 8: Context review
    if ctx_pending > 0:
        actions.append({
            "action_id": "ACT-CTX-CLR",
            "title": f"審核 Context Updates ({ctx_pending} 筆)",
            "category": "context_review",
            "risk_level": "low",
            "status": "available",
            "reason": f"有 {ctx_pending} 筆待審核的 context 更新",
            "required_confirmation": "Owner approve",
            "related_files": ["~/.hermes/process/context_update_pending_report.json"],
            "recommended_order": 8,
        })

    # ── Blocked / Observe / Needs Approval ──

    # Action: hermes-tg-bot (core infrastructure)
    actions.append({
        "action_id": "ACT-CI-TGBOT",
        "title": "hermes-tg-bot core infrastructure integration",
        "category": "core_infrastructure",
        "risk_level": "high",
        "status": "observe",
        "reason": "核心基礎設施（tg_interface），需 CI2+ 設計，目前已有 core_readonly_card",
        "required_confirmation": "Core Infrastructure Integration Design + Owner approval",
        "related_files": ["~/.hermes/process/CORE_INFRASTRUCTURE_INTEGRATION_DESIGN.md"],
        "recommended_order": 80,
    })

    # Action: trading-server
    actions.append({
        "action_id": "ACT-TRADING",
        "title": "接入 trading-server",
        "category": "plan_integration",
        "risk_level": "critical",
        "status": "blocked",
        "reason": "核心交易系統，涉及真實資金，Candidate D",
        "required_confirmation": "董事會 + final_confirm + dry-run",
        "related_files": ["~/.hermes/plans/trading-server/"],
        "recommended_order": 99,
    })

    # Action: arena
    actions.append({
        "action_id": "ACT-ARENA",
        "title": "接入百大競技場",
        "category": "plan_integration",
        "risk_level": "critical",
        "status": "blocked",
        "reason": "核心交易競技場，涉及交易，Candidate D",
        "required_confirmation": "董事會 + final_confirm + dry-run",
        "related_files": ["~/.hermes/plans/arena/"],
        "recommended_order": 99,
    })

    # Action: pos-backend
    actions.append({
        "action_id": "ACT-POS",
        "title": "接入 pos-backend",
        "category": "plan_integration",
        "risk_level": "critical",
        "status": "blocked",
        "reason": "POS 系統涉及金錢，Candidate D",
        "required_confirmation": "董事會 + final_confirm + dry-run",
        "related_files": ["~/.hermes/plans/pos-backend/"],
        "recommended_order": 99,
    })

    # Action: 啟動服務
    actions.append({
        "action_id": "ACT-SVC",
        "title": "啟動 inert PLAN 服務",
        "category": "service_activation",
        "risk_level": "high",
        "status": "observe",
        "reason": "觀察期內不啟動，等 Gateway 穩定後再考慮",
        "required_confirmation": "觀察期結束 + Owner 明確同意",
        "related_files": ["~/.hermes/plans/"],
        "recommended_order": 90,
    })

    # Action: 自動 TG context sync
    actions.append({
        "action_id": "ACT-TG-CTX",
        "title": "自動 TG Context Sync",
        "category": "automation",
        "risk_level": "medium",
        "status": "needs_approval",
        "reason": "目前 context 更新需人工 approve，自動化需設計安全機制",
        "required_confirmation": "Owner approval + safety design",
        "related_files": ["~/.hermes/process/"],
        "recommended_order": 50,
    })

    # Action: 解凍模組
    actions.append({
        "action_id": "ACT-UNFREEZE",
        "title": "解凍 Frozen 模組",
        "category": "module_management",
        "risk_level": "medium",
        "status": "observe",
        "reason": "觀察期結束前不解凍，需先確認無 incident",
        "required_confirmation": "觀察期結束 + incident 審查",
        "related_files": ["~/.hermes/process/"],
        "recommended_order": 60,
    })

    # Action: mcp-github readonly
    actions.append({
        "action_id": "ACT-MCP",
        "title": "Readonly integrate mcp-github",
        "category": "plan_integration",
        "risk_level": "medium",
        "status": "observe",
        "reason": "外部 API 依賴（GitHub），score=3，Candidate B，需先確認 API 安全邊界",
        "required_confirmation": "API 邊界設計 + Owner review",
        "related_files": ["~/.hermes/plans/mcp-github/"],
        "recommended_order": 70,
    })

    # 排序
    actions.sort(key=lambda x: x["recommended_order"])

    return actions






def generate_html(md_content):
    """把 markdown 轉成單檔 HTML"""
    # 簡易 md → html 轉換
    html_lines = []
    in_table = False
    in_list = False

    for line in md_content.split("\n"):
        # Headers
        if line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append(f"<h2>{line[3:]}</h2>")
        # Table
        elif line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if not in_table:
                html_lines.append("<table>")
                html_lines.append("<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
                in_table = True
            else:
                html_lines.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        elif line.startswith("|---"):
            continue
        # List
        elif line.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            text = line[2:]
            # Color code
            if "✅" in text:
                html_lines.append(f'<li class="ok">{text}</li>')
            elif "❌" in text:
                html_lines.append(f'<li class="error">{text}</li>')
            elif "⚠️" in text:
                html_lines.append(f'<li class="warn">{text}</li>')
            else:
                html_lines.append(f"<li>{text}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if in_table:
                html_lines.append("</table>")
                in_table = False
            if line.strip():
                html_lines.append(f"<p>{line}</p>")

    if in_table:
        html_lines.append("</table>")
    if in_list:
        html_lines.append("</ul>")

    body = "\n".join(html_lines)

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="utf-8">
<title>Hermes Governance Dashboard</title>
<style>
body {{ font-family: monospace; background: #1a1a1a; color: #e0e0e0; padding: 20px; max-width: 1000px; margin: 0 auto; }}
h1 {{ color: #00ff88; border-bottom: 2px solid #00ff88; padding-bottom: 8px; }}
h2 {{ color: #88ccff; border-bottom: 1px solid #333; padding-bottom: 4px; margin-top: 24px; }}
table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
td, th {{ padding: 4px 12px; border: 1px solid #333; text-align: left; }}
th {{ background: #2a2a2a; color: #88ccff; }}
tr:hover {{ background: #222; }}
.ok {{ color: #00ff88; }}
.warn {{ color: #ffaa00; }}
.error {{ color: #ff4444; }}
.frozen {{ color: #888; }}
ul {{ padding-left: 20px; }}
li {{ margin: 2px 0; }}
p {{ margin: 4px 0; }}
.footer {{ margin-top: 40px; padding-top: 8px; border-top: 1px solid #333; color: #666; font-size: 0.9em; }}
</style>
</head>
<body>
{body}
<div class="footer">Governance Dashboard v1.0 — 只讀，不執行 — {now_iso()[:19]}</div>
</body>
</html>"""


def main():
    print("Governance Dashboard Builder v1.0 (Phase GD1)")
    print()

    # 讀取資料源
    sources_ok = 0
    sources_fail = 0
    for name, path in [
        ("active_context", ACTIVE_CONTEXT),
        ("registry", REGISTRY_FILE),
        ("events_log", EVENTS_LOG),
        ("request_report", PROCESS_DIR / "tg_request_intake_report_v3.json"),
        ("review_state", PROCESS_DIR / "tg_request_review_state.json"),
        ("reply_state", PROCESS_DIR / "tg_reply_approval_state.json"),
        ("context_report", PROCESS_DIR / "context_update_pending_report.json"),
        ("up_queue", PROCESS_DIR / "tg_request_universal_queue.jsonl"),
    ]:
        if path.exists():
            sources_ok += 1
        else:
            sources_fail += 1
            print(f"  ⚠️ {name}: not found")

    print(f"  資料源: {sources_ok} ok, {sources_fail} missing")
    print()

    # 產生 markdown
    md = generate_md()
    MD_OUTPUT.write_text(md)
    print(f"  MD: {MD_OUTPUT}")

    # 產生 html
    html = generate_html(md)
    HTML_OUTPUT.write_text(html)
    print(f"  HTML: {HTML_OUTPUT}")

    # 摘要
    plans = get_plan_status()
    requests = get_pending_requests()
    review = get_review_state()
    reply = get_reply_state()

    print()
    print(f"  PLANs: {len(plans)}")
    print(f"  TG Requests: {requests['eligible']} eligible")
    print(f"  Review: {review['accepted']} accepted, {review['pending']} pending")
    print(f"  Replies: {reply['sent']} sent")
    print()
    print("  ✅ 只讀，未改任何來源檔")
    print("  ✅ 未啟動 server")


if __name__ == "__main__":
    main()








