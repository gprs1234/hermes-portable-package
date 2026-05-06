# Opus 4.7 架構檢視提示詞

直接貼給 Opus 4.7 即可：

---

你是一個資深的系統架構師。請仔細審查以下系統架構，針對每個環節給出具體的改進建議。

## 你的任務

審查一個 AI 自治管理系統的完整架構。這個系統的目標是：人類只在 Telegram 看通知，所有日常運維由 AI 自動處理。

## 系統概述

三層架構：
- Hermes（主 Agent）→ PLAN Registry（中央登記）→ PLAN Agents（各事業體經理）→ Worker Agents（工人）

核心理念：
1. 創造路徑即全貌 — 記住「怎麼來的」不只記住結果
2. 全自治 — AI 管 AI，人類只在結構性崩潰時介入
3. 經驗沉澱 — 重複做的事變成 skill，skill 可自動進化

## 已建組件

### PLAN Registry（中央管理）
- 檔案: ~/.hermes/plan_registry/plan_registry.py
- 功能: 註冊、心跳讀取、指令下達、全域健康概覽
- 目前 9 個資產，3 個有完整監控，5 個有部分監控，1 個無監控

### 百大競技場 Arena（最完整的自治系統）
數據流: MT4 EA → ea_bridge → simulator → signal_engine → referee → score_publisher → dashboard
PLAN Agent: 每 10 分鐘巡邏 A→B→C→D→E→F，自動修復，分派 Worker
Worker Agent: 查 skill → 執行 → 回報，6 個 skill（重啟、診斷、驗證）
策略: 5 模組 x ~85-100 策略，虛擬回測競爭，自動淘汰/遞補

### Trading Server
監控 server_file.py 進程 + ECMARKET EA 數據新鮮度
讀 arena/live_data/ 而非舊的 /mnt/c/trading/

### AI Company
監控 board_bot.py + watchdog.py
自動重啟能力

### Cron Jobs（11 個）
- PLAN Agent 自治巡邏 (10min) → Telegram
- bot-health-patrol (5min)
- system-health-check (30min)
- Trading Server 監控 (5min) → Telegram
- AI Company 監控 (5min) → Telegram
- memory-compress (weekly)
- log-cleanup (weekly)
- self-review (weekly)
- research x3 (daily/weekly)

### Skills（19 個）
涵蓋: 競技場管理、Agent 行為規範、多模型協作、Provider 路由、日誌管理、靈感引擎等

## 請審查以下問題

1. **架構完整性**: 三層架構（Hermes→PLAN→Worker）有什麼漏洞？單點故障在哪？
2. **自治程度**: 哪些環節還依賴人類？怎麼進一步自治？
3. **擴展性**: 加 10 個新事業體時架構撐得住嗎？
4. **安全**: API Key 管理、進程隔離、權限控制做好了嗎？
5. **效率**: 11 個 cron job 有重複嗎？有更高效的做法嗎？
6. **Skill 進化**: Worker 的 skill 系統怎麼自動進化？目前設計有什麼缺陷？
7. **跨 PLAN 關聯**: 一個 PLAN 的問題影響另一個時（如 EA 斷線影響 Arena + Trading Server），怎麼連鎖診斷？
8. **遺漏**: 有什麼應該被監控但沒有被監控的？

## 重要背景

- 系統跑在 WSL (Linux on Windows)
- Windows 端跑 MT4 EA，Linux 端跑所有 Python 服務
- WSL 的 pgrep 看不到背景進程，需要用數據新鮮度判斷
- 用戶(Owner)只用 Telegram 溝通，無法直接操作 Linux
- 用戶偏好：規則自動執行、不被動、反感「先不管」「有事叫我」

請逐項給出具體、可執行的建議。不要泛泛而談，要指出具體的檔案、函式、流程。
