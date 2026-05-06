# HB3: External Heartbeat Verification Design

日期: 2026-05-05
狀態: design only

---

## 一、目的

用獨立程序驗證 bot 是否真的在跑（不只是自報或被動推斷）。

信任鏈：
```
HB1 被動推斷 < HB2 自報 < HB3 外部驗證
```

HB3 是信任鏈的最高層：由獨立進程主動檢查目標 bot 的可達性。

---

## 二、驗證方式

### 方式 A: HTTP Health Endpoint（首選）
- bot 暴露 /health 或 /ping 端點
- HB3 checker 發 HTTP GET，檢查 status code + response time
- 適用：ai-dashboard (Flask), pos-backend (Cloudflare Worker)

### 方式 B: Process Check
- 檢查 bot 的 PID 是否存在
- 檢查 /proc/{pid}/status 是否正常
- 適用：hermes_bot.py, board_bot.py

### 方式 C: API Reachability
- 發 Telegram getMe API call 驗證 bot token 有效
- 不發送訊息，只查 bot 身份
- 適用：hermes-tg-bot, board-bot

### 方式 D: File Heartbeat Freshness
- 檢查 heartbeat.json 的 timestamp 是否在閾值內
- 最弱的驗證（只確認有人在寫，不確認 bot 活著）
- 適用：所有

---

## 三、設計

```python
# 偽代碼
for each module in core_infrastructure:
    result = verify(module)
    write_verification_result(module, result)

def verify(module):
    if module.has_http_endpoint:
        return http_check(module.health_url)
    elif module.has_pid:
        return pid_check(module.pid)
    elif module.has_telegram_bot:
        return telegram_getme(module.bot_token_ref)
    else:
        return file_freshness(module.heartbeat_path)
```

### 輸出
```json
{
  "plan_id": "hermes-tg-bot",
  "verified_at": "ISO 8601",
  "method": "telegram_getme",
  "result": "reachable",
  "response_time_ms": 150,
  "status": "HEALTHY",
  "health_source": "external_verified",
  "trust_level": "external",
  "external_verified": true,
  "confidence": "high"
}
```

---

## 四、安全規則

- 不得發送 Telegram 訊息（只用 getMe / getUpdates offset）
- 不得讀取或暴露 bot token
- 不得修改 bot 狀態
- 不得重啟 bot
- 驗證失敗只記錄，不自動修復
- 如果外部驗證結果與自報矛盾，以外部為準

---

## 五、排程

- 每 10 分鐘跑一次（和 watchdog cron 合併或獨立）
- 結果寫入 heartbeat.json（覆蓋 health_source 和 trust_level）
- 如果外部驗證通過：status=HEALTHY, external_verified=true
- 如果外部驗證失敗：保持現有 status，標 external_verified=false

---

## 六、實作順序

Phase HB3A: Design（本文件）
Phase HB3B: HTTP checker（ai-dashboard, pos-backend）
Phase HB3C: PID checker（hermes_bot.py, board_bot.py）
Phase HB3D: Telegram getMe checker（hermes-tg-bot, board-bot）
Phase HB3E: Dashboard 整合（顯示 external_verified 狀態）

---

## 七、與 HB1/HB2 的關係

```
HB1 OBSERVED    — 外部看活動紀錄推斷
HB2 SELF_REPORTED — bot 自己報
HB3 HEALTHY      — 獨立程序驗證通過

Dashboard 顯示:
  ✅ external_verified=true  — HB3 通過
  ⚠️ self_reported           — HB2 自報，未外部驗證
  ❓ observed                — HB1 被動推斷
  ❌ no_data                 — 無心跳
```

---

*HB3 Design — 2026-05-05*
