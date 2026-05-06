# HB2: Bot Self Heartbeat Design

日期: 2026-05-05
狀態: design only

---

## 一、目的

讓 bot 主動報告自己的健康狀態（自報），而非靠外部推斷。

目前：
- HB1 被動推斷：從活動紀錄推斷 hermes-tg-bot 狀態（status=OBSERVED）
- watchdog.py / board_bot.py 的 heartbeat 是 cron 寫的，不是 bot 自己寫的

HB2 要做的：
- bot 在自己的主循環中定期寫 heartbeat
- 包含 bot 視角的內部狀態（queue depth, error count, uptime）
- status=SELF_REPORTED（不是 HEALTHY，那是外部驗證的事）

---

## 二、設計

### 寫入路徑
```
~/.hermes/plan_registry/{bot_id}_heartbeat.json
```

### 寫入時機
- 每次 polling loop 迭代時更新（不額外開 thread）
- 或每 N 次迭代寫一次（避免 I/O 過頻）

### 欄位

```json
{
  "plan_id": "hermes-tg-bot",
  "timestamp": "ISO 8601",
  "status": "SELF_REPORTED",
  "health_source": "self_reported",
  "trust_level": "self",
  "confidence": "medium",
  "external_verified": false,
  "review_required": false,
  "uptime_seconds": 3600,
  "last_message_at": "ISO 8601",
  "messages_processed": 42,
  "errors_last_hour": 0,
  "queue_depth": 0,
  "memory_mb": 128,
  "bot_version": "1.0.0"
}
```

### 適用對象
- hermes_bot.py (大腦)
- board_bot.py (董事會)

### 不適用
- watchdog.py — 已有自己的 heartbeat 機制
- arena PLAN Agent — 已有巡邏 heartbeat

---

## 三、安全規則

- bot 不得把自己的 status 寫成 HEALTHY（只能 SELF_REPORTED）
- 不得覆蓋外部驗證的 heartbeat（如果已有 external_verified=true）
- 不得寫入 token / API key / 密碼
- 寫入失敗不得 crash bot 主循環
- heartbeat 檔案用 atomic write（先寫 .tmp 再 rename）

---

## 四、與現有機制的關係

```
HB1: 被動推斷（外部看活動紀錄）→ status=OBSERVED
HB2: 主動自報（bot 自己報）→ status=SELF_REPORTED
HB3: 外部驗證（獨立檢查器）→ status=HEALTHY

信任度: HB3 > HB2 > HB1
```

---

## 五、實作建議

Phase HB2A: Design（本文件）— 只設計，不改 bot
Phase HB2B: hermes_bot.py 加入 self heartbeat
Phase HB2C: board_bot.py 加入 self heartbeat
Phase HB2D: Dashboard 顯示 self-reported vs observed vs external

---

## 六、風險

- 低：只寫 heartbeat 檔案，不改 bot 核心邏輯
- 中：bot crash 可能導致 heartbeat 過期（但 watchdog 會偵測）
- 低：I/O 增加（每 loop 寫一個小 JSON）

---

*HB2 Design — 2026-05-05*
