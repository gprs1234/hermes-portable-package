# CLI→TG Sender 自動化設計

日期: 2026-05-05
狀態: design only

---

## 一、現狀

- CLI → TG reply 已可運作（E2E 驗通）
- 但每個 reply 都需要 Nomi 手動 approve_send
- 高風險內容需要 approve，但低風險重複性報告可以自動化

## 二、目標

低風險 reply 自動發送，高風險 reply 仍需人工確認。

## 三、自動發送條件

### 可自動發送（免確認）
- Cron 報告（如 Hermes 整合報告）
- 系統健康通知（watchdog 告警已修復）
- 競技場狀態摘要（health_score + issue count）
- [SILENT] 回應（不發送，自動跳過）

### 需要確認
- 任何包含建議/決策的回覆
- 任何涉及交易的回覆
- 任何包含敏感資訊的回覆
- 任何 risk_level = medium/high/critical

### 絕對不自動發
- 任何包含 token/key/password
- 任何涉及金錢操作
- 任何修改系統狀態的建議
- 任何董事會相關

## 四、分類邏輯

```python
def should_auto_send(reply_text, risk_level, request_type):
    # 自動發送
    if risk_level == "low" and request_type in ["cron_report", "health_check", "arena_status"]:
        return True
    # 需確認
    if risk_level in ["medium", "high", "critical"]:
        return False
    if contains_sensitive(reply_text):
        return False
    if has_decision(reply_text):
        return False
    # 預設自動
    return risk_level == "low"
```

## 五、安全規則

- 自動發送的訊息必須標記 `auto_sent: true`
- 必須寫入 audit log
- 自動發送失敗不 retry（走 RT4 retry policy）
- 每小時最多自動發送 N 條（防止洗版）
- 連續 N 次自動發送失敗 → 暫停自動發送，通知 Nomi

## 六、實作順序

Phase AS1: Design（本文件）
Phase AS2: 分類器（判斷哪些 reply 可自動發送）
Phase AS3: Auto-sender（整合到 reply pipeline）
Phase AS4: Dashboard 顯示 auto-send 統計

---

*CLI→TG Sender 自動化設計 v1.0*
