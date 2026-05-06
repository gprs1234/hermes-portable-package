# Active Context — 當前工作狀態
# 每次 session 結束自動更新，新 session 第一個讀取
# 更新日期: 2026-05-02

---

## 當前焦點

剛完成完整的自治系統架構建設。從「你是不是看不懂全貌」開始，建立了一整個組織系統。

## 今天完成的事（2026-05-01）

### 核心架構
- ✅ PLAN Agent — 自主巡邏 A→B→C→D→E→F
- ✅ Worker Agent — 查 skill 執行，冪等設計
- ✅ PLAN Registry — 中央管理 11 個資產
- ✅ PLAN Factory — 從點子到全自治 PLAN 的誕生引擎
- ✅ Watchdog — 獨立監控 PLAN 存活
- ✅ Conflict Detector — 多 PLAN 衝突偵測
- ✅ Board Connector — 董事會決議 → Hermes 橋接

### 組織架構（四層）
- ✅ 董事會 (決策層) — @WuBank_bot，只輸出
- ✅ Hermes (管理層) — @MyHermersAgent_bot，整合決策
- ✅ PLAN Agent (執行層) — 每 PLAN 獨立 bot
- ✅ Worker (勞動層) — 查 skill 執行

### 資訊流動修正
- ✅ 4 個 cron 改為 local（不直接推 TG）
- ✅ 建 Hermes 整合報告（唯一推 TG 的）
- ✅ 正確流動：PLAN→寫檔案→Hermes 讀取→分析→只推重要的

### 基礎設施
- ✅ Portable Package on GitHub
- ✅ Notion 串接（4 個資料庫 + 12 個頁面）
- ✅ API Keys 存 Notion（換機可用）
- ✅ .env chmod 600
- ✅ gen_strats.py/gen_opus46.py API Key 移除

### 問題修復
- ✅ ea_bridge 誤報（WSL pgrep → 數據新鮮度）
- ✅ Trading Server 數據來源（TMGM → ECMARKET）
- ✅ Worker 模板變數未替換
- ✅ /help HTML 轉義
- ✅ /plan 指令實作
- ✅ plan_agent.py 被清空後重建
- ✅ Cron jobs 合併（11→8）

### 架構檢視
- ✅ GPT-5.5 檢視完成
- ✅ 當前模型檢視完成
- ⏳ Opus 4.7 檢視待 cdnipcs 恢復

## 待辦事項

### 下一步
- [ ] 每個 PLAN 建專屬 TG Bot（PLAN Factory 已支援，待實際創建）
- [ ] 董事會實際連接到 board_connector（board_decisions.json 還沒被 Board Bot 產出）
- [ ] Worker skill 進化機制（失敗→分析→自動建議新 skill）
- [ ] 通知 outbox 整合到 Hermes 整合報告
- [ ] SQLite 遷移（PLAN >50 時）
- [ ] Windows heartbeat（需 Windows 端腳本）

### 已知問題
- Arena 85/100（3 模組策略不足：opus_4.6:85, deepseek:75, mimo:85）
- cdnipcs Claude 模型不穩定（503）
- cloudflared tunnel 每次重啟網址變

## 關鍵檔案位置

```
核心引擎: ~/.hermes/plan_registry/ (registry, watchdog, conflict_detector, board_connector)
PLAN Factory: ~/.hermes/plan_factory/plan_factory.py
Portable Package: ~/hermes-agent-system/ → github.com/<owner>/hermes-portable-package
Notion: workspace "Ching", 頁面 ID 353fb9a8-52cc-80e6-af2f-cd979c1aa6a7
競技場: <ARENA_ROOT>/arena/
Skills: ~/.hermes/skills/ (19 個) + arena/arena_control/worker_skills/ (6 個)
Knowledge: ~/.hermes/references/ (架構、檢視、設計、提示詞)
```

## Owner 偏好速查

- 溝通用繁體中文
- 介面偏好: TG > Web > CLI
- 不說「先不管」「有事叫我」
- 規則自動執行，改完回報
- 要看到創造路徑（怎麼來的），不只看結果
- 每個 PLAN 要專注自己的領域，不污染其他 PLAN

### Cline Memory Bank 整合
- ✅ 分析完成：我們比 Cline 更完整，只缺 active_context.md
- ✅ active_context.md 已建
- ✅ system_prompt 加入啟動流程（讀 active_context → 檢查 registry → 檢查 inbox）
- ✅ GitHub + Notion 同步完成
