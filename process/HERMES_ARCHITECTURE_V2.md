# Hermes 架構總覽 v2.0

日期: 2026-05-06
狀態: Production
作者: Hermes Agent + Owner

---

## 目錄

1. [系統總覽](#1-系統總覽)
2. [Agent Company OS](#2-agent-company-os)
3. [Arena 策略補位系統](#3-arena-策略補位系統)
4. [Key Pool & 多 Provider 管理](#4-key-pool--多-provider-管理)
5. [Governance Dashboard](#5-governance-dashboard)
6. [Integration Report](#6-integration-report)
7. [行為規範](#7-行為規範)
8. [檔案地圖](#8-檔案地圖)

---

## 1. 系統總覽

Hermes 是一個全自治 AI Agent 系統，管理多個事業體（百大競技場、Trading、POS 等）。
核心原則：**人類只在紛爭時介入，日常運營由 AI 自治。**

### 架構層級

```
┌─────────────────────────────────────────────┐
│  Owner（人類）— 最終決策者                    │
├─────────────────────────────────────────────┤
│  董事會 (Board) — Gateway 審批               │
├─────────────────────────────────────────────┤
│  Hermes Agent — 大腦（CLI + TG Bot）         │
│  ├── Agent Company OS                        │
│  ├── Governance Dashboard                    │
│  ├── Integration Report                      │
│  └── Key Pool Manager                        │
├─────────────────────────────────────────────┤
│  PLAN Agents — 各事業體自治管理者             │
│  ├── Arena PLAN Agent (plan_agent.py)        │
│  └── 未來: Trading PLAN Agent, POS PLAN Agent│
├─────────────────────────────────────────────┤
│  Worker Agents — 執行層                      │
│  ├── gen_module.py (策略生成器)              │
│  ├── referee_engine.py (裁判引擎)            │
│  └── worker_agent.py (任務執行)              │
└─────────────────────────────────────────────┘
```

---

## 2. Agent Company OS

把 Hermes 從「顧問型 Agent」升級為「一人公司作業系統」。

### 2.1 核心元件

| 元件 | 檔案 | 用途 |
|------|------|------|
| Business Unit Registry | `company/business_unit_registry.json` | 登記所有事業體 |
| Agent Registry | `company/agent_registry.json` | 7 個 C-Level Agent 定義 |
| Concept Cell Template | `company/03-sop/concept_cell_template.md` | 概念攝入範本 |
| Concept Intake | `scripts/concept_intake.py` | 自然語言→結構化 Concept Cell |
| Dept Review | `scripts/dept_review.py` | 7 Agent 自動審查 |
| Operational Patrol | `scripts/operational_patrol.py` | Functional Health 巡邏 |

### 2.2 C-Level Agents

| Agent | 職責 |
|-------|------|
| COO | 流程設計、SOP |
| CTO | 技術可行性、架構 |
| CFO | 成本分析、ROI |
| CMO | 市場分析、用戶 |
| CLO | 法規、合規 |
| CHRO | 人力、組織 |
| CIO | 資訊、數據 |

### 2.3 Concept Intake Flow

```
Owner 說一個念頭
      ↓
concept_intake.py 分類引擎（10 個分類）
  - new_business, existing_bu_problem, hypothesis,
    tech_infra, process_improvement, cost_optimization,
    compliance, market_expansion, partnership, other
      ↓
自動展開:
  - shape.necessary_parts（必須組成）
  - shape.unknowns（未知項）
  - cheapest_verification（最便宜驗證法）
      ↓
dept_review.py → 7 個 C-Level Agent 自動審查
      ↓
decision_readiness 評分 → 建議下一步
```

### 2.4 Operational Patrol

自動巡邏所有 Business Unit 的健康狀態：

- **Process Health**: 進程是否存活（plan_agent_report.json services）
- **Functional Health**: 功能是否正常（策略數量、EA 連線等）
- **User Visible Health**: 用戶可見影響

**關鍵規則**: process alive ≠ functional OK。Arena 進程跑著但策略不足 = degraded。

---

## 3. Arena 策略補位系統

### 3.1 架構

```
referee_engine.instant_death_patrol
      ↓ 偵測到策略缺口
replenishment_requests.json
      ↓
plan_agent.py --dispatch
      ↓ 分派任務
worker_agent.py → gen_module.py
      ↓ 生成策略
contestants/{module}/active/{id}.json
```

### 3.2 多 Provider Generator

`gen_module.py` — 通用策略生成器，支持 5 個模組、4 個 Provider：

| 模組 | Provider | Model | Base URL |
|------|----------|-------|----------|
| gpt_5.5 | banana2556 | gpt-5.5 | api.banana2556.com/v1 |
| opus_4.6 | cdnipcs | claude-sonnet-4.6 | aitoken.cdnipcs.com/v1 |
| opus_4.7 | cdnipcs | claude-sonnet-4.6 | aitoken.cdnipcs.com/v1 |
| deepseek_v4_pro | deepseek直連 | deepseek-chat | api.deepseek.com/v1 |
| mimo-v2-pro | xiaomi直連 | mimo-v2-pro | api.xiaomimimo.com/v1 |

### 3.3 環境變數

arena `.env` 需要的變數：

```
ARENA_BANANA_API_KEY     # banana2556 (GPT-5.5)
ARENA_BANANA_BASE_URL    # https://api.banana2556.com/v1
ARENA_CDNI_API_KEY       # cdnipcs (Opus)
ARENA_CDNI_BASE_URL      # https://aitoken.cdnipcs.com/v1
ARENA_DEEPSEEK_API_KEY   # DeepSeek 直連
ARENA_DEEPSEEK_BASE_URL  # https://api.deepseek.com/v1
ARENA_MIMO_API_KEY       # Xiaomi 直連
ARENA_MIMO_BASE_URL      # https://api.xiaomimimo.com/v1
ARENA_CLAUDE_API_KEY     # Anthropic (備用)
ARENA_CLAUDE_BASE_URL    # Anthropic endpoint
```

### 3.4 GPT-5.5 特殊處理

GPT-5.5 在 cdnipcs 上走 `/responses` 端點，長 prompt 間歇性回空。
解決方案：改用 banana2556，走標準 `/chat/completions`。

### 3.5 Retry 機制

gen_module.py 內建 3 次 retry，處理 API 間歇性失敗。

---

## 4. Key Pool & 多 Provider 管理

### 4.1 架構

```
key_pool.json          # Key Pool 配置
      ↓
key_rotator.py         # Key 管理器
  - status             # 看所有 key 狀態
  - check              # 查用量
  - rotate             # 手動切換
  - add                # 新增 key
  - dashboard          # 產生用量看板
      ↓
key_error_monitor.py   # 錯誤觸發自動切換
  - 偵測 401/429 錯誤
  - 連續 3 次 → 自動 rotate
```

### 4.2 Provider 一覽

| Provider | Key 數 | 用途 |
|----------|--------|------|
| banana2556 | 1 | GPT-5.5 |
| cdnipcs | 1 | Opus 4.6/4.7 |
| deepseek | 1 | DeepSeek v4 |
| xiaomi | 1 | MiMo v2 Pro |
| nvidia | 2 | 備用 DeepSeek |
| anthropic | 1 | Claude (備用) |
| gemini | 2 | Gemini (備用) |
| alibaba | 1 | Qwen (備用) |

### 4.3 自動輪換規則

- 用量達 95% → 自動切換下一個 key
- API 回 401/429 → 連續 3 次自動切換
- 切換後自動更新 config.yaml
- Dashboard Section 31 顯示所有 key 狀態

---

## 5. Governance Dashboard

### 5.1 架構

`governance_dashboard_builder.py` → 31 個 sections → Markdown + HTML

### 5.2 Sections

| Section | 內容 |
|---------|------|
| 1-20 | 系統監控、服務狀態、PLAN Registry |
| 21-25 | Cron Jobs、Board Items、Integration |
| 26 | Agent Company OS Overview |
| 27 | C-Level Agent Roster |
| 28 | Business Unit Operating Map |
| 29 | False Health / Functional Health Watch |
| 30 | Operational Patrol Report |
| 31 | API Key Usage Dashboard |

### 5.3 重建

```bash
cd ~/.hermes/process && python3 governance_dashboard_builder.py
```

---

## 6. Integration Report

### 6.1 架構

`integration_report_local.py` → 每 10 分鐘自動跑 → TG 推送

### 6.2 報告結構

```
🏛️ Hermes 整合報告
━━━━━━━━━━━━
🕐 巡邏時間
🟠/🟢 競技場健康狀態 + 分數
✅ 服務運行狀態
⚠️ 策略補位缺口（per module）
📌 補位請求狀態
🟡 為什麼還沒補上（如有）
📋 董事會
📊 PLAN 統計
━━━━━━━━━━━━
需要你: [條件式輸出]
```

### 6.3 條件式「需要你」

- 有缺 env var → 「補齊 XXX」
- 有 deficit 但 env 齊 → 「暫不需要；generator 可自動補位」
- 全滿 → 「暫不需要手動操作」

---

## 7. 行為規範

### 7.1 修復驗證標準 (FIX_VERIFICATION_STANDARD)

**修復的驗收標準是「問題消失」，不是「動作完成」。**

流程：
1. 定義問題（Before 狀態）
2. 列出完整修復步驟鏈
3. 逐一執行並驗證
4. 確認問題消失（After 狀態）
5. 報告 Before → Steps → After

### 7.2 通用行動規則 (UNIVERSAL_ACTION_RULE)

**看見問題 = 立即修。報告裡不能有未修的問題。**

規則：
1. 報告不是結束。「缺口」「缺少」「未完成」= 還沒做完
2. 唯一允許停下來：超出能力範圍 or 風險太高需人類確認
3. 報告最後一行必須是「已修復」或「修復中」
4. 自檢：報告裡有未修的問題嗎？我能修嗎？為什麼還沒修？

### 7.3 反例 vs 正例

```
❌ "opus_4.6 缺 6 個策略"（報告了但沒補）
✅ "opus_4.6 缺 6 個策略 → 已跑 generator 補滿"

❌ "env var 缺少 ARENA_XXX"（發現了但沒設）
✅ "env var 缺少 → 已補齊並驗證"

❌ "需要你補齊 XXX"（能自己做卻推給人類）
✅ "超出能力範圍：需要你提供 XXX，因為 YYY"
```

---

## 8. 檔案地圖

### 核心配置

```
~/.hermes/
├── config.yaml                    # 主配置
├── auth.json                      # 認證資訊
├── key_pool.json                  # Key Pool 配置
├── .env                           # 環境變數
├── references/
│   └── active_context.md          # Session 間上下文
├── process/
│   ├── governance_dashboard_builder.py
│   ├── governance_dashboard_report.md
│   ├── governance_dashboard_report.html
│   ├── integration_report_local.py
│   ├── FIX_VERIFICATION_STANDARD.md
│   └── EXISTING_PLAN_INTEGRATION_READINESS_DESIGN.md
├── company/
│   ├── business_unit_registry.json
│   ├── agent_registry.json
│   └── 03-sop/concept_cell_template.md
├── scripts/
│   ├── concept_intake.py          # 概念攝入
│   ├── dept_review.py             # 部門審查
│   ├── operational_patrol.py      # 健康巡邏
│   ├── key_rotator.py             # Key 管理
│   └── key_error_monitor.py       # 錯誤監控
└── skills/
    └── agent-behavior-spec/SKILL.md  # 行為規範 (Section 28-29)
```

### Arena

```
<ARENA_ROOT>/arena/
├── .env                           # Arena 環境變數
├── arena_control/
│   ├── plan_agent.py              # PLAN Agent
│   ├── worker_agent.py            # Worker Agent
│   ├── referee_engine.py          # 裁判引擎
│   ├── gen_module.py              # 通用策略生成器
│   ├── gen_strats.py              # Opus 4.6 生成器
│   ├── gen_opus46.py              # Opus 4.6 生成器 (備用)
│   ├── mimo_strategy_generator.py # MiMo 生成器
│   ├── plan_agent_report.json     # 健康報告
│   └── replenishment_requests.json # 補位請求
└── contestants/
    ├── gpt_5.5/active/            # 100+ 策略
    ├── opus_4.6/active/           # 100+ 策略
    ├── opus_4.7/active/           # 100+ 策略
    ├── deepseek_v4_pro/active/    # 100+ 策略
    └── mimo-v2-pro/active/        # 100+ 策略
```

### GitHub

```
https://github.com/<owner>/hermes-agent-system
├── scripts/                       # 所有腳本
├── process/                       # 流程文件
├── company/                       # Company OS
├── key_pool.json                  # Key Pool
└── governance_dashboard_report.*  # Dashboard
```

---

## 版本歷史

| 版本 | 日期 | 修改內容 |
|------|------|---------|
| v1.0 | 2026-05-04 | Gateway + Universal Protocol + Mobile Governance Loop |
| v2.0 | 2026-05-06 | Agent Company OS + Arena 補位 + Key Pool + 行為規範 |

---

*此文件由 Hermes Agent 自動生成，最後更新: 2026-05-06 18:20*
