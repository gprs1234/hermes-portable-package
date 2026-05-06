# 架構檢視報告 — 由當前模型（Mimo V2.5 Pro）產出
# 日期: 2026-05-01
# 備註: Opus 4.7 和 GPT-5.5 連線失敗（cdnipcs 503），由執行中的模型代替審查

---

## 1. 架構完整性 — 單點故障分析

### 🔴 嚴重單點故障

**Hermes Agent 本身**
- 所有 PLAN → Hermes → Telegram 的路徑都經過 Hermes
- 如果 Hermes gateway 掛了，所有自治報告都送不出去
- 目前 bot-health-patrol 有監控 hermes_bot，但 gateway 本身的監控不夠即時
- **建議**: 建立 watchdog 獨立於 Hermes 的緊急通知通道（如直接 curl Telegram API）

**PLAN Registry 的檔案鎖**
- 多個 cron job 同時讀寫 registry.json 可能造成 race condition
- 目前沒有檔案鎖機制
- **建議**: 加 `fcntl.flock()` 或改用 SQLite

**心跳檔案的單向性**
- 心跳只有 PLAN → Registry 的單向流
- Registry 沒有主動 ping PLAN 的能力（如果 PLAN 靜默死亡，Registry 不知道）
- **建議**: Registry 檢查心跳時間戳，超過 30 分鐘沒更新就報警

### 🟡 中度風險

**ea_bridge 的 WSL 進程偵測**
- 已用數據新鮮度替代 pgrep，但如果 ea_bridge 停止但 CSV 檔案碰巧被其他程式更新，會誤判
- **建議**: 加入 ea_bridge_status.json 的 synced_at 時間戳交叉驗證

**Worker Agent 的 skill 路徑**
- skill 檔案路徑是硬編碼在 worker_agent.py 裡的
- 如果目錄結構改變，Worker 會找不到 skill
- **建議**: skill 路徑改從 registry 或 config 讀取

---

## 2. 自治程度 — 還有哪些依賴人類

| 環節 | 目前狀態 | 可以自治嗎 | 建議 |
|---|---|---|---|
| MT4 EA 崩潰 | 需要人類重啟 Windows | ❌ 無法 | 建立 RDP 遠端重啟腳本 |
| Telegram Bot token 過期 | 需要人類更新 | ❌ 無法 | token 到期前 30 天推提醒 |
| 新策略生成 | 需要呼叫外部 API | ✅ 可以 | PLAN Agent 自動觸發 gen_strats.py |
| 策略淘汰後遞補 | 需要決定策略類型 | ✅ 可以 | 根據市場條件自動選擇策略模板 |
| Cloudflare Worker 部署 | 需要 wrangler CLI | ✅ 可以 | 建 deploy skill |
| 跨 PLAN 連鎖診斷 | 目前沒有 | ✅ 可以 | 建立依賴圖 + 連鎖觸發 |
| Skill 自動進化 | 目前沒有 | ✅ 可以 | Worker 執行失敗 → 分析 → 建議新 skill |

---

## 3. 擴展性 — 加 10 個事業體

### 目前的瓶頸

1. **cron job 數量**: 每個事業體至少 1 個 cron job，10 個新事業體 = +10 個 cron
   - 目前 11 個，加完變 21 個
   - cron scheduler 的精度和資源會受影響
   - **建議**: 合併同頻率的 cron job，用一個 job 跑所有 PLAN

2. **Registry 的線性掃描**: `health_overview()` 遍歷所有 PLAN，100 個 PLAN 時會慢
   - **建議**: 加索引，或只讀 dirty 標記的 PLAN

3. **Telegram 推播洪流**: 10 個 PLAN 同時出問題 = 10 則通知
   - **建議**: 建立通知聚合器，5 分鐘內的同類問題合併成一則

### 可以撐的部分
- Registry 的 JSON 結構是 dict，查找 O(1)
- 每個 PLAN 的心跳是獨立檔案，不會互相干擾
- Worker Agent 的 skill 是共享的，新事業體可以複用

---

## 4. 安全

### 🔴 必須立即修復

**gen_opus46.py 的 API Key 曾經硬編碼**
- 雖然剛修復了，但 git 歷史可能還有
- **建議**: 輪換這個 key，檢查 git history

**.env 檔案權限**
- `/home/<user>/projects/.env` 包含所有 API key
- 檢查權限是否 600
- **建議**: `chmod 600 ~/.env`

**Worker 的 command 執行**
- Worker 的 `_execute_skill` 會執行 shell command
- 如果 skill 檔案被篡改，可以執行任意命令
- **建議**: skill 的 command 類型加白名單機制

### 🟡 需要注意

**心跳檔案沒有簽名**
- 任何人都可以寫入假心跳
- 目前在同一台機器上風險低，但如果將來分散部署要考慮
- **建議**: 心跳加 HMAC 簽名

---

## 5. 效率 — Cron Job 合併建議

### 目前 11 個 Cron Job

| 頻率 | Job | 建議 |
|---|---|---|
| 5min | bot-health-patrol | 合併 |
| 5min | Trading Server 監控 | 合併 |
| 5min | AI Company 監控 | 合併 |
| 10min | PLAN Agent 自治巡邏 | 保留 |
| 10min | arena-plan-agent | ⚠️ 重複！刪除 |
| 30min | system-health-check | 保留 |
| daily | research-trading | 保留 |
| weekly | research-ai | 保留 |
| weekly | research-models | 保留 |
| weekly | memory-compress | 保留 |
| weekly | log-cleanup | 保留 |
| weekly | self-review | 保留 |

### 建議
1. **刪除 arena-plan-agent** (3e5e7bdbc181) — 跟 PLAN Agent 自治巡邏重複
2. **合併三個 5min job** 為一個「全域健康巡邏」— 減少 cron scheduler 負擔
3. **總計**: 11 → 8 個

---

## 6. Skill 進化 — 目前的缺陷

### Worker Skill 系統的問題

1. **沒有「學習」機制**
   - Worker 執行成功/失敗只是計數 +1
   - 沒有分析「為什麼失敗」「能不能改進」
   - **建議**: 執行失敗時，Worker 記錄錯誤上下文，下次遇到類似問題自動調整

2. **Skill 是靜態的**
   - skill 檔案建好後不會自動更新
   - 沒有版本控制
   - **建議**: skill 加 version 欄位，Worker 執行時比較版本，舊版自動標記

3. **沒有 skill 共享機制**
   - Arena 的 restart_service skill 不能被 Trading Server 用
   - **建議**: 建立通用 skill 層（generic/）+ 事業體專屬層（arena/）

4. **沒有 skill 測試**
   - 新 skill 建好後直接上線，沒有 dry-run
   - **建議**: skill 加 `test_mode`，第一次執行時只診斷不執行

### 建議的進化流程

```
問題出現 → Worker 找不到 skill → 基礎診斷 → 記錄 gap
  ↓ (出現 3 次以上)
自動建立 skill draft → test_mode 執行 → 人工確認 → 正式上線
  ↓ (執行 10 次以上)
分析成功率 → 如果 < 80% → 自動優化步驟
```

---

## 7. 跨 PLAN 關聯 — 連鎖診斷

### 目前的問題

EA 斷線同時影響：
- Arena (ea_bridge 沒數據)
- Trading Server (ea_data.json 過時)
- signal_engine (信號品質下降)

但這三個 PLAN 各自獨立報告，沒有人把它們串起來。

### 建議：建立依賴圖

```python
DEPENDENCY_GRAPH = {
    "mt4-ea": ["arena.ea_bridge", "trading-server"],
    "ea_bridge": ["arena.simulator", "arena.signal_engine"],
    "arena.simulator": ["arena.referee", "arena.score_publisher"],
    "arena.score_publisher": ["arena.dashboard"],
}
```

**連鎖診斷流程**:
1. mt4-ea 報 CRITICAL
2. Registry 查依賴圖 → 找到 affected: [arena.ea_bridge, trading-server]
3. 自動檢查這些節點的健康
4. 合併報告：「MT4 EA 斷線 → 影響 Arena 和 Trading Server」

---

## 8. 遺漏清單

| 遺漏項目 | 嚴重度 | 說明 |
|---|---|---|
| POS Backend 無監控 | MEDIUM | Cloudflare Worker 掛了沒人知道 |
| AI Dashboard 無監控 | LOW | Flask app 掛了只是看不到看板 |
| hermes_gateway 心跳 | HIGH | 核心網關沒有獨立心跳 |
| mcp-github 心跳 | MEDIUM | GitHub 工具掛了影響 repo 操作 |
| 磁碟空間監控 | MEDIUM | WSL 磁碟滿了會導致所有服務崩潰 |
| 記憶體監控 | MEDIUM | Python 進程可能 OOM |
| 網路連線監控 | HIGH | 外網斷了所有 API 呼叫失敗 |
| cron job 執行監控 | MEDIUM | cron 掛了沒人知道 |
| 備份機制 | HIGH | 策略檔案、心跳、registry 沒有備份 |
| 日誌輪轉 | LOW | arena 的 .out.log 會無限增長 |
| 策略多樣性監控 | MEDIUM | 可能生成一堆相似策略 |

---

## 總結：優先修復清單

### 立即（今天）
1. ~~刪除重複 cron job arena-plan-agent~~
2. 檢查 .env 檔案權限 (chmod 600)
3. Registry 加心跳超時報警

### 本週
4. 合併三個 5min cron job
5. 建立跨 PLAN 依賴圖
6. 加磁碟/記憶體/網路監控
7. 建立 hermes_gateway 獨立心跳

### 下週
8. Worker skill 進化機制（失敗分析 → 自動建議新 skill）
9. 通知聚合器（避免推播洪流）
10. POS Backend + ai-dashboard 監控
11. 備份機制
