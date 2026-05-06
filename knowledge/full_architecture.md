# Owner 帝國 — 全系統架構清單

**建立日期**: 2026-05-01
**目的**: 給 Opus 4.7 檢視用 — 完整列出每個組件做什麼、怎麼連的、有什麼問題

---

## 一、核心原則（Owner 的設計哲學）

1. **創造路徑即全貌** — 不只記住結果，要記住「怎麼來的」，出問題才能沿路徑排查
2. **全自治** — AI 管 AI，人類只在結構性崩潰時介入
3. **輕量化本體** — 重型資料外包到 references/，本體只留指針
4. **經驗沉澱** — 重複做的事變成 skill，不常做的事擴展 skill
5. **規則自動執行** — 不被動記住，主動做，做完回報

---

## 二、架構層級

```
Owner（人類，只看 Telegram 通知）
  │
  ▼
Hermes（主 Agent，CLI + Telegram）
  │  - 整合所有 PLAN 的報告
  │  - 決策：自動處理 or 上報人類
  │  - 管理 PLAN Registry
  │
  ▼
PLAN Registry（中央登記處）
  │  ~/.hermes/plan_registry/plan_registry.py
  │  - 登記所有 PLAN Agent
  │  - 讀取心跳、發送指令
  │  - 目前 9 個資產
  │
  ▼
PLAN Agents（各事業體的經理）
  │  - 自主巡邏
  │  - 發現問題 → 自動修 or 分派 Worker
  │  - 寫心跳給 Registry
  │
  ▼
Worker Agents（工人）
     - 查 skill → 執行 → 驗證 → 回報
     - 沒有 skill → 建議新 skill
```

---

## 三、PLAN Registry（中央管理系統）

**檔案**: `~/.hermes/plan_registry/plan_registry.py`
**功能**: 註冊、查詢、監控所有 PLAN Agent

### 9 個已登記資產

| ID | 名稱 | 領域 | 監控狀態 | 分數 | 說明 |
|---|---|---|---|---|---|
| arena | 百大交易競技場 | trading | ✅ 有 PLAN+Worker+心跳 | 100/100 | 5 模組 x 100 策略競技場 |
| trading-server | Trading Server | trading | ⚠️ 有監控腳本 | 60/100 | server_file.py，讀 EA 數據 |
| hermes-gateway | Hermes Gateway | infrastructure | ⚠️ 有 cron 監控 | N/A | 核心網關，掛了=全斷 |
| hermes-tg-bot | Hermes TG Bot | infrastructure | ⚠️ 有 cron 監控 | N/A | @Previewtrade_bot |
| mcp-github | GitHub MCP | infrastructure | ⚠️ 有 cron 監控 | N/A | GitHub 工具伺服器 |
| board-bot | 董事會 Bot | ai-company | ✅ 有監控腳本 | 100/100 | board_bot.py |
| watchdog | AI Company 看門狗 | ai-company | ✅ 有監控腳本 | 100/100 | watchdog.py |
| ai-dashboard | AI 視覺化 | visualization | ❌ 無監控 | N/A | Flask app.py |
| pos-backend | POS 後台 | pos | ❌ 無監控 | N/A | Cloudflare Worker |

### 通訊協定
- **心跳**: 每個 PLAN 寫 `plan_heartbeat.json` → Registry 隨時可讀
- **指令**: Hermes 寫 `plan_command.json` → PLAN 讀取執行 → 寫 `plan_response.json`
- **報告**: PLAN 寫 `plan_agent_report.json` → cron 讀取推播到 Telegram

---

## 四、百大競技場（Arena）— 最完整的自治系統

### 4.1 數據流 A→B→C→D→E→F

```
ECMARKET MT4 EA (XAUUSD)
  │
  ▼
(A) ea_bridge.py [每5秒]
  │  讀 MT4 CSV → live_data/*.csv + signals/ea_bridge_status.json
  │
  ▼
(B) arena_simulator.py [每30秒]
  │  讀 live_data + 策略.py → trade_logs/*.json (虛擬回測)
  │
  ▼
(C) signal_engine.py [每15秒]
  │  讀 live_data + 策略.py → proposed_signal_xauusd.json (信號選拔)
  │
  ▼
(D) referee_engine.py [每小時巡邏 + 週五結算]
  │  讀 trade_logs → leaderboard + elimination + replenishment
  │
  ▼
(E) score_publisher.py [每30秒]
  │  import referee → leaderboard/*.json
  │
  ▼
(F) export_dashboard_data.py → dashboard_data.json → HTML 看板
```

### 4.2 核心檔案

| 檔案 | 角色 | 路徑 |
|---|---|---|
| plan_agent.py | PLAN Agent — 巡邏+分派 | arena/arena_control/ |
| worker_agent.py | Worker Agent — 執行任務 | arena/arena_control/ |
| ea_bridge.py | MT4 數據橋接 | arena/arena_control/ |
| arena_simulator.py | 虛擬回測引擎 | arena/arena_control/ |
| signal_engine.py | 信號選拔 | arena/arena_control/ |
| referee_engine.py | 裁判（評分+淘汰） | arena/arena_control/ |
| score_publisher.py | 排行榜發布 | arena/arena_control/ |
| export_dashboard_data.py | 儀表板匯出 | arena/arena_control/ |
| gen_strats.py | 策略生成（cdnipcs API） | arena/arena_control/ |
| gen_opus46.py | 策略生成（Opus 4.6） | arena/arena_control/ |
| mimo_strategy_generator.py | 策略生成（Mimo） | arena/arena_control/ |
| setup_arena.py | 初始化 | arena/ |
| start_arena.ps1 | 啟動全部服務 | arena/ |

### 4.3 Worker Skills（說明書庫）

| Skill | 用途 | 任務類型 |
|---|---|---|
| restart_service.json | 重啟任何 Arena 服務 | repair |
| check_ea_connection.json | 檢查 EA 連線、帳戶、價格 | diagnose |
| validate_strategies.json | 驗證策略 META 格式 | validate |
| check_data_freshness.json | 檢查 CSV/JSON 更新時間 | diagnose |
| diagnose_simulator.json | 診斷模擬器狀態和錯誤 | diagnose |
| refill_strategies.json | 檢查策略數量、遞補需求 | generate |

### 4.4 策略格式

```python
STRATEGY_META = {id, name, module, source, timeframe, description, tags, parameters, exit_rules}
def generate_signal(current_bar, history) -> {action, lots, stop_loss, take_profit, confidence, reasoning}
```
- history: dict {"M15": [...bars], "H1": [...bars], ...}
- current_bar: dict {open, high, low, close, volume}
- 模組: gpt_5.5, opus_4.6, opus_4.7, deepseek_v4_pro, mimo-v2-pro
- 目標: 每模組 100 策略

### 4.5 Cron Jobs（競技場相關）

| Job ID | 名稱 | 頻率 | 推播 | 說明 |
|---|---|---|---|---|
| 689ba9cd2f2b | PLAN Agent 自治巡邏 | 每10分鐘 | Telegram | plan_agent.py --fix --dispatch |
| 3e5e7bdbc181 | arena-plan-agent | 每10分鐘 | local | 舊版 PLAN（skill-based） |

### 4.6 已知問題

| 問題 | 嚴重度 | 狀態 |
|---|---|---|
| gen_strats.py 和 gen_opus46.py 功能重複 | LOW | 已知，待統一 |
| history 參數格式衝突（單TF vs 多TF） | HIGH | 已知，待修 |
| 頂層目錄遺留（舊版空殼） | LOW | 已知 |
| mimo 命名不一致（- vs _） | LOW | 已知 |
| score_publisher 呼叫 referee private method | MEDIUM | 已知 |

---

## 五、Trading Server

**監控腳本**: `~/.hermes/scripts/trading_server_monitor.py`
**功能**: server_file.py 進程 + ECMARKET EA 數據
**數據來源**: arena/live_data/ (非 /mnt/c/trading/)
**心跳**: `~/.hermes/plan_registry/trading_server_heartbeat.json`
**分數**: 60/100（server_file.py 進程問題）

---

## 六、AI Company

**監控腳本**: `~/.hermes/scripts/ai_company_monitor.py`
**監控對象**: board_bot.py + watchdog.py
**心跳**: 
- `~/.hermes/plan_registry/board_bot_heartbeat.json`
- `~/.hermes/plan_registry/watchdog_heartbeat.json`
**分數**: 100/100 + 100/100

---

## 七、基礎設施

### 7.1 Hermes Agent
- **Gateway**: hermes gateway run --replace（核心網關）
- **CLI**: hermes 命令行介面
- **Telegram Bot**: hermes_bot.py（@Previewtrade_bot）
- **MCP**: mcp-server-github（GitHub 工具）

### 7.2 Cron Jobs（系統維護）

| Job | 頻率 | 用途 |
|---|---|---|
| bot-health-patrol | 每5分鐘 | 檢查 hermes_bot + board_bot |
| system-health-check | 每30分鐘 | 檢查全部 9 個服務 |
| memory-compress-weekly | 每週日 3am | 記憶壓縮 |
| log-cleanup-weekly | 每週日 4am | 日誌清理 |
| self-review-weekly | 每週一 8am | 自我審視 |
| research-trading-daily | 每天 9am | 交易研究 |
| research-ai-weekly | 每週一 10am | AI 研究 |
| research-models-weekly | 每週一 11am | 模型研究 |

### 7.3 Skills（19 個）

| 類別 | Skill | 用途 |
|---|---|---|
| trading | arena-patrol | 競技場全自治系統 |
| trading | arena-plan-agent | 競技場 PLAN Agent |
| software | mt4-python-bridge | MT4-Python 橋接 |
| software | system-monitor | 9 服務健康檢查 |
| software | agent-behavior-spec | Agent 行為規範 |
| software | agent-workflow | Agent 執行紀律 |
| software | bot-lifecycle | Bot 生命週期管理 |
| software | provider-router | Provider 路由 |
| software | log-manager | 日誌管理 |
| software | memory-cleanup | 記憶清理 |
| software | hermes-update | Hermes 更新程序 |
| software | plan | Plan 模式 |
| software | writing-plans | 寫實施計劃 |
| software | multi-agent-collaboration | 多模型協作 |
| software | reverse-engineer-codebase | 反向工程 codebase |
| productivity | secretary-mode | 秘書模式 |
| productivity | outsourcer-pattern | 外包商模式 |
| productivity | inspiration-engine | 靈感引擎 |
| agents | hermes-agent | Hermes Agent 配置 |

---

## 八、外部系統

| 系統 | 位置 | 連接方式 | 狀態 |
|---|---|---|---|
| ECMARKET MT4 EA | Windows | ea_bridge.py 讀 CSV | ✅ 運行中 |
| POS Backend | Cloudflare Workers | API | ❓ 無監控 |
| Telegram | @Previewtrade_bot | Gateway + hermes_bot.py | ✅ 運行中 |

---

## 九、檔案結構速覽

```
~/.hermes/
├── plan_registry/
│   ├── plan_registry.py          # 中央 PLAN 管理
│   ├── registry.json             # 登記資料
│   ├── *_heartbeat.json          # 各 PLAN 心跳
│   └── *_command.json / *_response.json  # 指令通道
├── scripts/
│   ├── trading_server_monitor.py # Trading 監控
│   ├── ai_company_monitor.py     # AI Company 監控
│   ├── arena_health_check.py     # 競技場健康檢查
│   ├── arena_deep_audit.py       # 競技場深度審計
│   ├── arena_dual_notify.py      # 雙向通知
│   ├── tg_notify.py              # TG 推送
│   └── provider_router.py        # Provider 路由
├── skills/                       # 19 個 skill
├── references/                   # 外包商（重型資料）
└── session_archives/             # Session 存檔

<ARENA_ROOT>/arena/
├── arena_control/
│   ├── plan_agent.py             # PLAN Agent
│   ├── worker_agent.py           # Worker Agent
│   ├── worker_skills/            # 6 個 Worker skill
│   ├── ea_bridge.py              # EA 橋接
│   ├── arena_simulator.py        # 模擬器
│   ├── signal_engine.py          # 信號引擎
│   ├── referee_engine.py         # 裁判
│   ├── score_publisher.py        # 排行榜
│   ├── gen_strats.py             # 策略生成
│   └── *_state.json / *_log.json # 狀態檔
├── contestants/{module}/active/  # 策略檔案
├── live_data/                    # 即時行情 CSV
├── signals/                      # EA 狀態 + 信號
├── leaderboard/                  # 排行榜 JSON
└── dashboard/                    # 儀表板
```

---

## 十、給 Opus 4.7 的檢視問題

1. **架構完整性**: 這個三層架構（Hermes→PLAN→Worker）有什麼漏洞？有沒有單點故障？
2. **自治程度**: 哪些環節還是依賴人類？怎麼進一步自治？
3. **擴展性**: 如果要加 10 個新事業體，架構撐得住嗎？
4. **安全**: API Key 管理、權限隔離做好了嗎？
5. **效率**: cron job 會不會太多？有沒有重複監控？
6. **經驗沉澱**: Worker 的 skill 系統設計合理嗎？怎麼自動進化？
7. **跨 PLAN 關聯**: 一個 PLAN 的問題影響另一個時，怎麼連鎖診斷？
8. **遺漏**: 有什麼應該被監控但沒有被監控的？

---

## 十一、Universal Protocol（通用流程層）

**建立日期**: 2026-05-04
**文件**: `~/.hermes/process/HERMES_UNIVERSAL_PROTOCOL.md`

所有事情（不只是建 PLAN）都必須遵循的 12 個階段：

```
Stage 0: Intake           — 問題接收
Stage 1: Clarify          — 釐清目標與限制
Stage 2: Context Gathering — 蒐集上下文
Stage 3: Hypothesis       — 形成假設
Stage 4: Verification     — 驗證假設
Stage 5: Debate           — 補強與反方
Stage 6: Decision         — 決策
Stage 7: Preview          — 預覽方案
Stage 8: Approval         — 授權與 final confirm
Stage 9: Execution        — 執行
Stage 10: Validation      — 驗收
Stage 11: Memory          — 沉澱成 SOP
```

風險分級決定走多遠：
- Low: Stage 0-6 → 直接執行 → Stage 10-11
- Medium: Stage 0-9 完整走
- High: Stage 0-10 + 董事會
- Critical: Stage 0-11 + dry-run + preview + final confirm

---

## 十二、Gateway v1（PLAN 建構事件系統）

**建立日期**: 2026-05-04
**狀態**: v1.0 封版
**文件**: `~/.hermes/gateway/GATEWAY_V1_SUMMARY.md`

Universal Protocol 的 PLAN 建構特化版。

```
CLI 討論 → proposal.submit_to_board
  → board_connector → 董事會投票
  → board.approved → gateway 驗證
  → plan.build.requested → preview
  → approve_execute → final_execute_confirm
  → formal inert PLAN build
  → registry + heartbeat → CLI completed
```

20 種事件類型，82/82 安全測試通過。

核心元件：
- gateway_processor.py — 事件路由
- real_plan_builder.py — Preview 產生
- execute_approval.py — 授權管理
- formal_plan_builder.py — 正式 inert PLAN 建構

---

## 十三、PLAN Build Manifest Standard

**建立日期**: 2026-05-04
**文件**: `~/.hermes/process/PLAN_BUILD_MANIFEST_STANDARD.md`

PLAN 建構的子規範：
- build_manifest schema
- files_to_create 格式（含 purpose/template/validation）
- preview hash 規則
- executor compliance rules
- 驗收標準

---

## 十四、PLAN Type Profiles

**建立日期**: 2026-05-04
**文件**: `~/.hermes/process/PLAN_TYPE_PROFILES.md`

8 種 PLAN 類型模板：
- telegram_bot / api_service / dashboard / worker
- trading_module / research_project / crm_system / generic_plan

每種類型有建議檔案、tech_stack、測試方向。
Executor 依照 build_manifest 執行，不依照 profile 硬編碼。
