# Metadata Review — board-bot / watchdog / trading-server

日期: 2026-05-05
需 Owner 確認: 是

---

## 狀態

三個 PLAN 的 heartbeat 都已通過 HM1-HM3 遷移，有 health_source 和 trust_level。
唯一的 gap: `external_verified = False`（HB3 外部驗證尚未實作）。

## 建議動作

確認 `external_verified = False` 為正確狀態（表示「已 cross-check 但未經獨立外部驗證」）。

不需要額外檢查。只需要 Owner 確認：「這三個的 external_verified=false 是對的，我接受。」

## 三個 PLAN 的證據

### board-bot
- status: HEALTHY
- health_source: cross_checked
- trust_level: verified
- external_verified: false（待確認）
- 證據: board_bot.py 進程活著 (pid 檢查)，board_connector.py 每 2 分鐘監聽
- 風險: LOW（不涉及交易）

### watchdog
- status: HEALTHY
- health_source: cross_checked
- trust_level: verified
- external_verified: false（待確認）
- 證據: watchdog.py 每 5 分鐘 cron 執行，剛才成功跑過（材料管理 archived skip）
- 風險: LOW（不涉及交易）

### trading-server
- status: HEALTHY
- health_source: cross_checked
- trust_level: verified
- external_verified: false（待確認）
- 證據: trading_server_monitor.py 每 10 分鐘 cron，heartbeat timestamp 新鮮
- 風險: MEDIUM（涉及交易，但本次只確認 metadata，不碰交易邏輯）

## 確認後的動作

如果 Owner 確認，patch 三個 heartbeat：
- `external_verified: false`（明確標記）
- `metadata_reviewed_by: Owner`
- `metadata_reviewed_at: <timestamp>`

不改 status、不改 health_source、不改 trust_level。

---

*等 Owner 確認後執行*
