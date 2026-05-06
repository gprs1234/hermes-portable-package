# Service Activation 設計

日期: 2026-05-05
狀態: design only — blocked until 5/7

---

## 一、現狀

Gateway v1 封版觀察期: 5/4 ~ 5/7
正式 PLAN 狀態: INERT（不自動啟動服務）
觀察期內不解凍、不啟動服務。

## 二、觀察期結束後（5/8+）

### 可啟動的服務
- plan-ff1139da: Gateway 測試 PLAN
- test-formal-demo: Gateway 測試 PLAN

### 啟動流程
```
Owner 確認要啟動
  → 董事會投票（plan_registry.board_connector）
  → board.approved
  → Gateway 驗證
  → preview（顯示啟動後果）
  → approve_execute
  → final_confirm
  → 啟動服務
  → 監控 10 分鐘
  → 回報結果
```

### 安全規則
- 不自動啟動任何服務
- 必須董事會 + Owner 雙重確認
- 啟動後 10 分鐘內監控異常自動回滾
- 啟動日誌寫入 audit trail

## 三、不啟動的服務

- trading-server: 涉及真實資金，需更長觀察期
- arena: 涉及交易，需更長觀察期
- pos-backend: 外部 Cloudflare Worker，需獨立評估

## 四、5/7 後的第一步

1. 檢查 Gateway v1 觀察期紀錄
2. 確認無異常事件
3. 提案啟動 plan-ff1139da（測試用）
4. 走完整啟動流程

---

*Service Activation 設計 v1.0 — 5/7 後生效*
