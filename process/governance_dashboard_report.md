# Hermes Governance Dashboard
產生時間: 2026-05-06T11:44:45.849733+08:00

## 1. System Overview

Hermes Mobile Governance Loop v1 MVP
- 七大模組: 全部完成
- 狀態: frozen（觀察期）
- 交易系統: 未接入
- 百大競技場: 未接入

### Health Trust Summary
- Heartbeats: 17 total — HEALTHY=6 (verified=1, unverified=5), INERT=2, CRITICAL=2, UNKNOWN=7
- Metadata applied (HM3): 17 / 17

### Health Trust Legend

| Status | Trust Level | Meaning | Allowed Conclusion | Not Allowed | Next Step |
|--------|------------|---------|-------------------|-------------|-----------|
| GAP | none | 無 heartbeat / 無資料 | 未知 | 推斷健康/故障 | 建立 heartbeat 機制 |
| OBSERVED | passive | 有活動跡象，未外部驗證 | 最近有活動 | 確認健康 / 確認運行中 | external verification |
| SELF_REPORTED | self | 模組自己回報 | 模組認為自己正常 | 確認健康 | 交叉驗證 |
| HEALTHY | verified | 外部驗證通過 | 健康 | — | 定期重新驗證 |
| INERT | declared | 正式存在但未啟動 | 非故障，設計如此 | 推斷為 down | 需要時手動啟動 |
| STALE | weak_passive | 超過 24h 無活動 | 可能有問題 | 確認故障 | 檢查 bot / 服務 |
| CRITICAL | anomaly | 明確異常信號 | 有問題 | 忽略 | 立即調查 |
| UNKNOWN | none | 資料不足 | 未知 | 推斷任何狀態 | 補充資料源 |

## 2. Frozen Modules

| 模組 | 狀態 |
|------|------|
| Gateway v1 | frozen |
| Context Sync | frozen |
| Reply Channel | frozen |
| Request Intake | frozen |
| 交易系統 | 未接入 |
| 百大競技場 | 未接入 |

## 3. PLAN Status

總計: 13 個 PLAN (active: 5, inert: 2)

| PLAN ID | Name | Status | Mode | Trust |
|---------|------|--------|------|-------|
| arena | 百大交易競技場 | 🟢 active | — | 🔵 active (no heartbeat) |
| trading-server | Trading Server | 🟢 active | — | 🟡 HEALTHY (not external verified) |
| board-bot | 董事會 Bot | 🟢 active | — | 🟡 HEALTHY (not external verified) |
| watchdog | AI Company Watchdog | 🟢 active | — | 🟡 HEALTHY (not external verified) |
| keyword-image-gen | 關鍵詞生圖 | 🟢 active | — | 🔵 active (no heartbeat) |
| 材料管理 | 材料管理 | ❓ archived | — | — (no heartbeat) |
| test-formal-demo | CRM 客戶關係管理正式版 | ⚪ inert | formal | ⬜ INERT (declared) |
| plan-ff1139da | Gateway v1 inert PLAN 測試 | ⚪ inert | formal | ⬜ INERT (declared) |
| hermes-gateway | Hermes Agent Gateway | 🔵 registered | — | — (no heartbeat) |
| hermes-tg-bot | Hermes Telegram Bot | 🔵 registered | — | 🟢 HEALTHY (external verified) |
| mcp-github | GitHub MCP Server | 🔵 registered | — | — (no heartbeat) |
| ai-dashboard | AI Visualization Dashboard | 🔵 registered | — | — (no heartbeat) |
| pos-backend | POS Backend (Cloudflare Worker) | 🔵 registered | — | ❓ UNKNOWN |

## 4. Pending TG Requests

- 掃描到: 88 筆
- eligible: 28 筆
- Review: pending=75, accepted=2, rejected=1, clarify=1
- UP Queue: queued=0, analyzed=2

## 5. Pending Context Updates

- 掃描到: 6 筆
- 待審核: 0 筆

## 6. Pending TG Replies

- 已發送: 5
- 已批准: 0
- 已拒絕: 1

## 7. Recent Events (last 10)

| 時間 | 類型 | 來源 | ID |
|------|------|------|-----|
| 2026-05-05T11:39:51 | tg.request.received | tg_hermes_agent_cli | EVT-REQ-20260505-2e3 |
| 2026-05-05T11:39:51 | tg.request.received | tg_hermes_agent_cli | EVT-REQ-20260505-800 |
| 2026-05-05T11:39:51 | tg.request.received | tg_hermes_agent_cli | EVT-REQ-20260505-e6b |
| 2026-05-05T11:39:51 | tg.request.received | tg_hermes_agent_cli | EVT-REQ-20260505-0c2 |
| 2026-05-05T16:30:14 | tg.reply.requested | universal_protocol_processor | EVT-RPL-E2E2-2026050 |
| 2026-05-05T16:30:45 | tg.reply.approved | hermes_opus47 | EVT-RPL-APR-20260505 |
| 2026-05-05T16:31:45 | tg.reply.approved | hermes_opus47 | EVT-RPL-APR-20260505 |
| 2026-05-05T16:32:29 | tg.reply.sent | hermes_opus47 | EVT-RPL-SENT-2026050 |
| 2026-05-05T18:05:37 | tg.reply.requested | cli | EVT-RPL-20260505-f95 |
| 2026-05-05T18:06:00 | tg.reply.approved | cli | EVT-RPL-APR-20260505 |

## 8. Known Gaps

| Gap | 狀態 |
|-----|------|
| TG↔CLI Context Sync | ✅ 有解法 |
| CLI→TG Reply Channel | ✅ 有解法 |
| Reply 錯發 Incident | ✅ 有解法 |

## 9. Action Checklist

| # | Action | Category | Risk | Status | Reason |
|---|--------|----------|------|--------|--------|
| 1 | Readonly integrate: mcp-github | plan_integration | 🟢 low | ✅ available | Candidate A PLAN (registered)，score 低 |
| 2 | 擴充 Dashboard detail 區塊 | dashboard | 🟢 low | ✅ available | 目前只顯示 plan-ff1139da，可擴充更多 PLAN |
| 3 | 清理 Pending TG Request (75 筆) | request_review | 🟢 low | ✅ available | 有 75 筆待審核 request |
| 4 | 整理 Governance SOP 文件 | documentation | 🟢 low | ✅ available | process/ 目錄文件可整理為標準化 SOP |
| 5 | 建立 Readonly Health Check | monitoring | 🟢 low | ✅ available | 定時檢查已接入 PLAN 的狀態一致性 |
| 6 | 設計 Modify Preview 流程 | design | 🟢 low | ✅ available | PI3 前置設計：修改 PLAN 前先 preview diff |
| 7 | 自動 TG Context Sync | automation | 🟡 medium | ⚠️ needs_approval | 目前 context 更新需人工 approve，自動化需設計安全機制 |
| 8 | 解凍 Frozen 模組 | module_management | 🟡 medium | 👁️ observe | 觀察期結束前不解凍，需先確認無 incident |
| 9 | Readonly integrate mcp-github | plan_integration | 🟡 medium | 👁️ observe | 外部 API 依賴（GitHub），score=3，Candidate B，需先確認 API 安全邊界 |
| 10 | hermes-tg-bot core infrastructure integration | core_infrastructure | 🔴 high | 👁️ observe | 核心基礎設施（tg_interface），需 CI2+ 設計，目前已有 core_readonly_card |
| 11 | 啟動 inert PLAN 服務 | service_activation | 🔴 high | 👁️ observe | 觀察期內不啟動，等 Gateway 穩定後再考慮 |
| 12 | 接入 trading-server | plan_integration | ⛔ critical | 🚫 blocked | 核心交易系統，涉及真實資金，Candidate D |
| 13 | 接入百大競技場 | plan_integration | ⛔ critical | 🚫 blocked | 核心交易競技場，涉及交易，Candidate D |
| 14 | 接入 pos-backend | plan_integration | ⛔ critical | 🚫 blocked | POS 系統涉及金錢，Candidate D |

## 10. Suggested Safe Next Actions

1. **Readonly integrate: mcp-github** — Candidate A PLAN (registered)，score 低
   - risk: 🟢 low
   - confirmation: none (readonly)
   - related: ~/.hermes/plans/mcp-github/
2. **擴充 Dashboard detail 區塊** — 目前只顯示 plan-ff1139da，可擴充更多 PLAN
   - risk: 🟢 low
   - confirmation: none
   - related: ~/.hermes/process/governance_dashboard_builder.py
3. **清理 Pending TG Request (75 筆)** — 有 75 筆待審核 request
   - risk: 🟢 low
   - confirmation: 逐筆 review
   - related: ~/.hermes/gateway/inbox/tg_request/
4. **整理 Governance SOP 文件** — process/ 目錄文件可整理為標準化 SOP
   - risk: 🟢 low
   - confirmation: none
   - related: ~/.hermes/process/
5. **建立 Readonly Health Check** — 定時檢查已接入 PLAN 的狀態一致性
   - risk: 🟢 low
   - confirmation: none
   - related: ~/.hermes/process/governance_dashboard_builder.py
6. **設計 Modify Preview 流程** — PI3 前置設計：修改 PLAN 前先 preview diff
   - risk: 🟢 low
   - confirmation: none (純設計文件)
   - related: ~/.hermes/process/

## 11. Blocked / Deferred Actions

- **接入 trading-server** (🚫 BLOCKED)
  - reason: 核心交易系統，涉及真實資金，Candidate D
  - risk: critical
  - confirmation: 董事會 + final_confirm + dry-run
- **接入百大競技場** (🚫 BLOCKED)
  - reason: 核心交易競技場，涉及交易，Candidate D
  - risk: critical
  - confirmation: 董事會 + final_confirm + dry-run
- **接入 pos-backend** (🚫 BLOCKED)
  - reason: POS 系統涉及金錢，Candidate D
  - risk: critical
  - confirmation: 董事會 + final_confirm + dry-run
- **解凍 Frozen 模組** (👁️ OBSERVE)
  - reason: 觀察期結束前不解凍，需先確認無 incident
  - risk: medium
  - confirmation: 觀察期結束 + incident 審查
- **Readonly integrate mcp-github** (👁️ OBSERVE)
  - reason: 外部 API 依賴（GitHub），score=3，Candidate B，需先確認 API 安全邊界
  - risk: medium
  - confirmation: API 邊界設計 + Owner review
- **hermes-tg-bot core infrastructure integration** (👁️ OBSERVE)
  - reason: 核心基礎設施（tg_interface），需 CI2+ 設計，目前已有 core_readonly_card
  - risk: high
  - confirmation: Core Infrastructure Integration Design + Owner approval
- **啟動 inert PLAN 服務** (👁️ OBSERVE)
  - reason: 觀察期內不啟動，等 Gateway 穩定後再考慮
  - risk: high
  - confirmation: 觀察期結束 + Owner 明確同意
- **自動 TG Context Sync** (⚠️ NEEDS APPROVAL)
  - reason: 目前 context 更新需人工 approve，自動化需設計安全機制
  - risk: medium
  - confirmation: Owner approval + safety design

## 12. Observation Window

| Module | Frozen Since | Days in Observation |
|--------|-------------|---------------------|
| Gateway v1 | 2026-05-04 | 1d remaining |
| Context Sync v1 | 2026-05-04 | 1d remaining |
| Reply Channel v1 | 2026-05-04 | 1d remaining |
| Request Intake | 2026-05-04 | 1d remaining |

- 觀察期截止: 2026-05-07
- 目前狀態: 🔵 觀察期進行中
- 已知 incidents: 2
- 建議: 繼續觀察，不改動模組

## 13. Pending Work Queues

| Queue | Pending | Details |
|-------|---------|---------|
| TG Request Review | 75 | 待 Owner review 的 TG request |
| Context Update Review | 0 | 待審核的 context 更新 |
| Reply Pending | 0 | 已批准待發送的 reply |
| Universal Queue | 0 | 待分析的通用佇列項目 |
| PLAN Integration Candidates | 1 | 可做 readonly integration 的候選 PLAN |
| **Total** | **76** | **所有待辦項目總計** |

## 14. Safety Lock Summary

目前生效的安全鎖：

| Lock | Status | Description |
|------|--------|-------------|
| No Trading Integration | 🔒 ACTIVE | trading-server / arena / pos-backend 全部未接入 |
| No Auto Execution from TG | 🔒 ACTIVE | TG request 必須經過 review + approval 流程 |
| No Direct active_context Write | 🔒 ACTIVE | context 更新需 Owner approve + apply 兩步確認 |
| No Service Activation | 🔒 ACTIVE | inert PLAN 不可透過 Dashboard 啟動 |
| No Board Bypass | 🔒 ACTIVE | 所有決策需經過董事會投票機制 |
| Final Confirm Required | 🔒 ACTIVE | high/critical 操作需 final_confirm 才執行 |
| Observation Period Lock | 🔒 ACTIVE | 5/4~5/7 不改動任何 frozen 模組 |
| Readonly PLAN Integration | 🔒 ACTIVE | 已接入 PLAN 僅限 view_only 操作 |

---

## 15. PLAN Detail: plan-ff1139da

**Integration Status**: readonly_integrated
**Allowed Actions**: view_only
**Forbidden Actions**: start / modify / delete / deploy

- plan_id: plan-ff1139da
- name: Gateway v1 inert PLAN 測試
- status: inert
- mode: formal

### Heartbeat
- status: INERT
- active: False
- service_started: False
- auto_start: False
- health_score: 0
- last_heartbeat: 2026-05-04T16:12:09
- issues: INERT: 等待服務啟動

### Manifest
- plan_name: Gateway v1 inert PLAN 測試
- build_event_id: EVT-20260504-0b40
- decision_id: BD-20260504-V1TEST
- correlation_id: COR-20260504-077b
- approved_by: Owner
- built_at: 2026-05-04T16:12:09
- files_created: 4
- registry_entry_added: True

### Files Present
- README.md (311 bytes)
- config.yaml (445 bytes)
- heartbeat.json (596 bytes)
- logs/.keep (0 bytes)
- plan_manifest.json (732 bytes)
- reports/.keep (0 bytes)

### Reports / Logs
- reports: 0 files
- logs: 0 files

### Registry Entry
- plan_id: plan-ff1139da
- name: Gateway v1 inert PLAN 測試
- status: inert
- source: gateway
- decision_id: BD-20260504-V1TEST
- correlation_id: COR-20260504-077b
- created_at: 2026-05-04T16:12:09.306618+08:00
- auto_restart: False
- auto_start: False
- heartbeat_interval: 300
- mode: formal

## 16. PLAN Detail: test-formal-demo

**Integration Status**: readonly_integrated
**Allowed Actions**: view_only
**Forbidden Actions**: start / modify / delete / deploy

- plan_id: test-formal-demo
- name: CRM 客戶關係管理正式版
- status: inert
- mode: formal

### Heartbeat
- status: INERT
- active: False
- service_started: False
- auto_start: False
- health_score: 0
- last_heartbeat: 2026-05-04T15:53:06
- issues: INERT: 等待服務啟動

### Manifest
- plan_name: CRM 客戶關係管理正式版
- build_event_id: EVT-20260504-dadd
- decision_id: BD-FINAL
- correlation_id: COR-FINAL
- approved_by: Owner
- built_at: 2026-05-04T15:53:06
- files_created: 4
- registry_entry_added: True

### Files Present
- README.md (332 bytes)
- config.yaml (433 bytes)
- heartbeat.json (599 bytes)
- logs/.keep (0 bytes)
- plan_manifest.json (724 bytes)
- reports/.keep (0 bytes)

### Reports / Logs
- reports: 0 files
- logs: 0 files

### Registry Entry
- plan_id: test-formal-demo
- name: CRM 客戶關係管理正式版
- status: inert
- source: gateway
- decision_id: BD-FINAL
- correlation_id: COR-FINAL
- created_at: 2026-05-04T15:53:06.234619+08:00
- auto_restart: False
- auto_start: False
- heartbeat_interval: 300
- mode: formal

## 17. PLAN Factory Readonly Card: 材料管理

**Integration Status**: factory_readonly_card
**Allowed Actions**: view_only
**Forbidden Actions**: start / modify / delete / deploy / restart / create_bot / write_token / connect_pos

### Registry
- plan_id: 材料管理
- name: 材料管理
- status: archived
- domain: pos
- owner: Owner
- heartbeat_path: /home/<user>/.hermes/plan_factory/plans/材料管理/heartbeat.json

### Blueprint
- description: 我想做一個材料管理系統，可以從手機查庫存，倉庫進出貨時要即時通知，資料不用很大，可能之後接 POS
- data_layer: json
- planned_integrations: pos-backend
- language: python
- framework_api: FastAPI
- external_actions_require_human: 1

### Heartbeat
- status: archived
- source: template
- pid: None
- score: 0
- timestamp: 2026-05-05T20:58:42

### Files Present
- .archived.json (176 bytes)
- blueprint.json (3723 bytes)
- bot_config.yaml (592 bytes)
- bot_register.md (694 bytes)
- bot_template.py (6670 bytes)
- heartbeat.json (671 bytes)
- main.py (1773 bytes)
- monitor.py (4974 bytes)
- skill.json (885 bytes)

### Skill Declaration
- skill_name: restart_材料管理
- version: 1.0.0
- triggers: 3
- actions_declared: 2
- note: skill actions are displayed only; Dashboard must not execute restart/check commands.

### Safety Notes
- 此卡只代表已能被治理 dashboard 看見，不代表 PLAN 已啟動。
- status=not_started，不是 active service。
- planned POS integration 仍未接入，任何 POS/金錢相關動作都 blocked。
- Telegram bot token / BotFather / .env 均未處理。


## 18. Core Infrastructure Status

核心基礎設施模組 — 不適用一般 PLAN Detail，獨立顯示。

### hermes-tg-bot (tg_interface)

- module_id: hermes-tg-bot
- name: Hermes Telegram Bot
- role: tg_interface — Owner 的對話窗口
- description: Owner 的對話窗口 — hermes_bot.py。掛了 = Owner 無法跟系統溝通
- status: registered
- domain: infrastructure
- owner: Owner
- criticality: MAXIMUM

#### Health
- health_source: external_verified — external verified
- self_monitoring_risk: false（介面層，不監控自己）
- heartbeat_status: HEALTHY
- trust_level: verified
- heartbeat_confidence: high
- last_heartbeat: 2026-05-05T08:33:10
- polling_alive: inferred
- reply_channel_alive: inferred
- context_sync_alive: inferred
- last_chat_history: 2026-05-04T17:16:43
- last_reply_sent: 2026-05-04T21:51:19
- last_request: 2026-05-04T20:18:38
- last_context_sync: 2026-05-04T17:51:57

#### Dependencies
- dependency_direction: outbound（依賴外部，無模組依賴它）
- depends_on: hermes-gateway, telegram bot token, chat_id
- location: ~/projects/ai_company/
- process: python3 hermes_bot.py
- gateway_bot: @Previewtrade_bot
- auto_restart: True

#### Actions
- integration_status: core_readonly_card
- allowed_actions: view_only
- forbidden_actions: start / modify / delete / restart / self_approve / send_message
- manual_review_required: true

#### Activity Summary（from Governance Loop）
- reply_sent: 5
- reply_approved: 0
- reply_rejected: 1
- requests_total: 88
- requests_eligible: 28

## 19. Health Source Audit / Metadata Incomplete

Heartbeat metadata 可信度檢查。此區塊只讀，不修復、不重啟、不改 status。

### Audit Summary
- total_heartbeats: 10
- missing_health_source: 0
- not_external_verified: 3
- stale_timestamp: 3
- needs_review: 6

### Metadata Completeness Score (GD4)

每個 heartbeat 的 4 個關鍵 metadata 欄位填寫狀態。

| Plan ID | Status | health_source | confidence | trust_level | ext_verified | Score |
|---------|--------|---------------|------------|-------------|--------------|-------|
| ai_dashboard | OK | ✅ | ❌ | ✅ | ⚠️ | 3/4 |
| board-bot | HEALTHY | ✅ | ❌ | ✅ | ⚠️ | 3/4 |
| hermes-tg-bot | HEALTHY | ✅ | ❌ | ✅ | ✅ | 3/4 |
| mt4_ea | CRITICAL | ✅ | ❌ | ✅ | ⚠️ | 3/4 |
| plan-ff1139da | INERT | ✅ | ❌ | ✅ | ⚠️ | 3/4 |
| pos_backend | UNKNOWN | ✅ | ❌ | ✅ | ⚠️ | 3/4 |
| system_resource | UNKNOWN | ✅ | ❌ | ✅ | ⚠️ | 3/4 |
| test-formal-demo | INERT | ✅ | ❌ | ✅ | ⚠️ | 3/4 |
| trading-server | HEALTHY | ✅ | ❌ | ✅ | ⚠️ | 3/4 |
| watchdog | HEALTHY | ✅ | ❌ | ✅ | ⚠️ | 3/4 |

### Completeness Distribution
- 3/4: ai_dashboard, board-bot, hermes-tg-bot, mt4_ea, plan-ff1139da, pos_backend, system_resource, test-formal-demo, trading-server, watchdog (10)

### Archived Plans
- 材料管理: archived (never started, watchdog skip enabled)

### Metadata Incomplete
| Plan ID | Status | Missing / Issue | Risk Handling | Recommended Action |
|---------|--------|-----------------|---------------|--------------------|
| board-bot | HEALTHY | not_external_verified | manual review — core infrastructure | 標示 external_verified=false，或執行外部驗證 |
| trading-server | HEALTHY | not_external_verified | blocked — trading related | 標示 external_verified=false，或執行外部驗證 |
| watchdog | HEALTHY | not_external_verified | manual review — core infrastructure | 標示 external_verified=false，或執行外部驗證 |

### Passive / Not External Verified
- 無 passive-only heartbeat。

### Critical Signals
| Plan ID | Status | Source | External Verified | Meaning |
|---------|--------|--------|-------------------|---------|
| mt4_ea | CRITICAL | manual_observed | False | critical remains critical; source labels context only |

### Safety Notes
- Dashboard 不得把 CRITICAL 轉成 HEALTHY。
- Dashboard 不得自動 patch board-bot / watchdog / trading-server。
- trading-server 仍 blocked，任何交易相關操作需董事會 + Owner final_confirm。
- mt4_ea 的 manual_observed 只代表 CRITICAL 有人工接受的上下文，不代表修復。

## 20. Automation Candidate Queues

顯示 RI4B / RT4B 的候選狀態。此區塊只讀，不建立事件、不發送 Telegram。

### RI4B Result-to-Reply Eligibility
- queue_items: 2
- eligible_candidates: 1
- ineligible_items: 1
- reply_events_created: 0
- telegram_sent: false
- REQ-20260504-041: eligible=False reason=already_replied
- REQ-20260505-087: eligible=True reason=none

### RT4B Reply Retry Preview
- reply_events_scanned: 5
- eligible_retry_previews: 0
- retry_previews_created: 0
- telegram_sent: false
- EVT-RPL-20260504-2bed: eligible=False reason=status_not_failed:sent, already_sent
- EVT-RPL-20260504-f8b4: eligible=False reason=status_not_failed:sent, already_sent
- EVT-RPL-20260505-c2a2: eligible=False reason=status_not_failed:pending_send_approval
- EVT-RPL-20260505-f95f: eligible=False reason=status_not_failed:sent, already_sent
- EVT-RPL-E2E-20260505-80f6: eligible=False reason=status_not_failed:sent, already_sent

### Safety Notes
- RI4B 不得直接建立 tg.reply.requested event。
- RT4B 不得 retry sent event。
- 任何 candidate 仍需 Reply Channel v1 approve_send + preflight + send_confirm。

## 21. TG Desktop Agent E2E Validation

- generated_at: 2026-05-05T18:06:45.127032+08:00
- result: 10 / 10 checks passed
- mode: safe_e2e_validation_no_send
- telegram_sent_by_validator: false
- services_started: false
- trading_touched: false

### Checks
| Check | Pass | Notes |
|-------|------|-------|
| E2E-01_core_files | True | ok |
| E2E-02_reports | True | ok |
| E2E-03_context_sync | True | pending_approval=0 |
| E2E-04_request_intake | True | eligible=28; reviews=4; queue_lines=2 |
| E2E-05_universal_status | True | ok |
| E2E-06_reply_channel | True | sent_count=5; sent_to_myhermes=4 |
| E2E-07_dashboard | True | ok |
| E2E-08_health_trust | True | missing_health_source=3 |
| E2E-09_secret_scan | True | ok |
| E2E-10_live_inbound_readiness | True | message_count=90 |

### Live Test Note
- CLI→TG outbound 已有實際 sent event。
- 新鮮 TG→CLI inbound 仍需要 Owner 從 TG 發一則真人訊息，因為 agent 無法替人類製造 inbound user message。

## 22. PLAN Detail: ai-dashboard (Readonly Integrated)

- plan_id: ai-dashboard
- name: AI Visualization Dashboard
- domain: visualization
- status: registered
- integration: readonly_integrated (PI4)
- allowed_actions: view_only
- forbidden_actions: start / modify / delete / deploy / restart

### Heartbeat
- service: ai_dashboard
- type: flask
- status: OK
- message: Service is running and responding
- check process: PASS
- check port: PASS
- check http: PASS

### Safety
- 只讀整合，未修改 PLAN
- 未修改 registry
- 未啟動/停止服務
- Flask app.py 狀態由 heartbeat 回報

## 23. Core Infrastructure: Gateway / Board-Bot / Watchdog

核心基礎設施擴充卡片 — hermes-tg-bot 已在 Section 18。

### Hermes Gateway (hermes-gateway)
- role: gateway — CLI↔董事會↔TG 事件路由核心
- criticality: MAXIMUM
- registry_status: registered
- domain: infrastructure
- integration: core_readonly (CI3)
- allowed_actions: view_only
- forbidden_actions: start / modify / delete / deploy / restart

### Board Bot (board-bot)
- role: ai-company — 董事會決議引擎
- criticality: HIGH
- registry_status: active
- domain: ai-company
- heartbeat_status: HEALTHY
- last_heartbeat: 2026-05-06T03:40:01.104847+00:00
- integration: core_readonly (CI3)
- allowed_actions: view_only
- forbidden_actions: start / modify / delete / deploy / restart

### Watchdog (watchdog)
- role: ai-company — 全域監控看門狗
- criticality: HIGH
- registry_status: active
- domain: ai-company
- heartbeat_status: HEALTHY
- last_heartbeat: 2026-05-06T03:40:01.105047+00:00
- integration: core_readonly (CI3)
- allowed_actions: view_only
- forbidden_actions: start / modify / delete / deploy / restart

## 24. PLAN Detail: pos-backend (Readonly Integrated)

- plan_id: pos-backend
- name: POS Backend (Cloudflare Worker)
- description: pos — Cloudflare Worker API
- status: registered
- domain: pos
- integration: readonly_integrated (PI5)
- allowed_actions: view_only
- forbidden_actions: start / modify / delete / deploy / restart
- heartbeat_status: UNKNOWN
- heartbeat_message: Auto-fix not possible - external Cloudflare Worker

### Safety
- 只讀整合，未修改 PLAN / registry / 服務

## 25. PLAN Detail: keyword-image-gen (Readonly Integrated)

- plan_id: keyword-image-gen
- name: Keyword Image Generator
- description: creative — AI 圖片生成
- status: active
- domain: creative
- integration: readonly_integrated (PI6)
- allowed_actions: view_only
- forbidden_actions: start / modify / delete / deploy / restart

### Safety
- 只讀整合，未修改 PLAN / registry / 服務

## 26. Agent Company OS Overview

Hermes 從顧問型 Agent 升級為一人公司作業系統。

- operating_model: Agent Company OS (轉型中)
- owner: Owner (方向設定 / 最終決策)
- company_os: Hermes (日常運作 / 自動化)
- c_level_agents: 7 (CEO, COO, CTO, CFO, CMO, CHRO, CAO)
- business_units: 1 (arena / 百大交易競技場)
- concept_cells: 0 (待建立)
- phase: AC2 — Dashboard + Registry 建立中

## 27. C-Level Agent Roster

| Agent ID | Role | Department | Manager | Mission |
|----------|------|------------|---------|---------|
| ceo | Chief Executive Officer | Executive | Owner | 確保公司方向正確、資源分配合理、各部門協調運作 |
| coo | Chief Operating Officer | Operations | CEO | 確保所有 Business Units 的日常運作正常、流程順暢、績效達標 |
| cto | Chief Technology Officer | Technology | CEO | 確保技術基礎設施穩定、代碼品質、系統架構合理 |
| cfo | Chief Financial Officer | Finance | CEO | 監控 API 成本、Token 用量、資源使用效率 |
| cmo | Chief Marketing Officer | Marketing | CEO | 管理品牌、對外溝通、用戶體驗 |
| chro | Chief Human Resources Officer | People | CEO | 管理 Agent 職責分配、工作量平衡、技能發展 |
| cao | Chief Assurance Officer | Assurance | CEO | 防止虛假健康報告、確保驗證獨立性、攔截未驗證高風險操作 |

### Authority Summary
- **ceo**: forbidden=[direct_trading, bypass_approval_chain]
- **coo**: forbidden=[modify_trading_logic, approve_own_changes]
- **cto**: forbidden=[skip_code_review, deploy_without_test]
- **cfo**: forbidden=[approve_own_expenses, access_trading_funds]
- **cmo**: forbidden=[publish_without_review, modify_user_data]
- **chro**: forbidden=[modify_agent_mission, approve_own_role_change]
- **cao**: forbidden=[approve_own_verification, bypass_block]

## 28. Business Unit Operating Map

### 百大交易競技場 (arena)
- type: arena
- status: degraded
- lifecycle: operating
- owner: Owner
- primary_c_level: COO, CTO, CAO
- process_health: alive
- functional_health: degraded
- user_visible_health: needs_review
- health_score: 70
- current_issues:
  - active_deficit_total=22 (gpt_5.5:8, opus_4.6:5, opus_4.7:3, deepseek_v4_pro:2, mimo-v2-pro:4)
  - arena model API env incomplete
  - replenishment blocked until API keys configured
- next_action: Configure arena model API env vars to allow strategy replenishment

## 29. False Health / Functional Health Watch

防止 process alive 但 functional degraded 的虛假健康報告。

| Business Unit | Process Health | Functional Health | User-Visible | Deficit | Blocking |
|---------------|---------------|-------------------|--------------|---------|----------|
| arena | alive | degraded | needs_review | 22 | arena model API env incomplete |

### False Health Rules
- 不得報 HEALTHY 如果任何 model < 100 active strategies
- 不得報 HEALTHY 如果 replenishment pending
- 不得報 HEALTHY 如果 leaderboard stale
- functional_health 獨立於 process_health
- CAO 有權攔截虛假健康報告

## 30. Operational Patrol Report

- Patrol Time: 2026-05-06T11:28:48
- BUs Checked: 1
- Overall: degraded
- False Health Alerts: 1

#### 百大交易競技場 (arena)
- Process: alive
- Functional: degraded
- User-Visible: needs_review
- ⚠️ FALSE HEALTH: process alive but functional degraded!
- Issue: active_deficit=100 (active=0, target=100)


## 31. API Key Usage Dashboard

- Rotation Threshold: 95%

#### cdnipcs
- 🟢 cdnipcs-key-01: active | usage=? | cdnipcs 主力 key
- ⚪ cdnipcs-key-02: standby | usage=? | cdnipcs 備用 key

#### xiaomi
- 🟢 xiaomi-key-01: active | usage=? | xiaomi 主力 key

---
*Governance Dashboard v3.2 — Company OS + Patrol + Key Pool — 只讀，不執行*