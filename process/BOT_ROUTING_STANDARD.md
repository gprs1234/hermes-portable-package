# Bot Routing Standard — v1.0
# 所有 Telegram 發送端的路由規則
# 日期: 2026-05-05

---

## 一、Bot 定義

| Bot 代號 | Telegram Bot | 角色 | Token Key | .env 變數 |
|----------|-------------|------|-----------|-----------|
| 大腦 | @MyHermersAgent_bot | Hermes Agent CLI 主腦 | HERMES_BOT_TOKEN | TELEGRAM_BOT_TOKEN, HERMES_BOT_TOKEN |
| 百大 | @Previewtrade_bot | 百大競技場通知 | ARENA_BOT_TOKEN | ARENA_BOT_TOKEN |
| 董事會 | @WuBank_bot | 董事會治理 | BOARD_BOT_TOKEN | BOARD_BOT_TOKEN |

---

## 二、路由規則

### 大腦 (MyHermersAgent_bot) — 收所有治理類訊息

| 發送端 | 路徑 | 觸發條件 |
|--------|------|----------|
| Hermes CLI send_message | hermes-telegram channel | CLI 用戶指令回覆 |
| Cron deliver | telegram:6823341162 | 排程任務報告 |
| tg_reply_sender.py | process/ | TG request 處理結果回覆 |
| tg_notify.py | scripts/ | 系統級通知（watchdog, 健康檢查, 異常） |
| notification_outbox.py | plan_registry/ | PLAN 狀態變更通知 |

### 百大 (Previewtrade_bot) — 只收競技場相關

| 發送端 | 路徑 | 觸發條件 |
|--------|------|----------|
| arena_dual_notify.py | scripts/ | 競技場健康報告、策略異常、排名變動 |

### 董事會 (WuBank_bot) — 只收董事會相關

| 發送端 | 路徑 | 觸發條件 |
|--------|------|----------|
| board_bot.py | ai_company/ | 董事會決議、投票通知 |

---

## 三、分類規則（新訊息該去哪）

```
收到要發通知的請求
  │
  ├─ 是競技場相關？(策略異常/排名/比賽結果)
  │   → 百大 (ARENA_BOT_TOKEN)
  │
  ├─ 是董事會相關？(投票/決議/治理)
  │   → 董事會 (BOARD_BOT_TOKEN)
  │
  ├─ 其他所有？(系統健康/PLAN 狀態/TG 回覆/cron 報告/異常告警)
  │   → 大腦 (TELEGRAM_BOT_TOKEN)
  │
  └─ 不確定？
      → 大腦 (預設)
```

---

## 四、Token 來源層級

Token routing 必須依目標 bot fail-closed：

```
大腦 / Hermes 類通知:
  1. HERMES_BOT_TOKEN
  2. TELEGRAM_BOT_TOKEN（只允許在它同樣指向大腦 bot 時作為相容 fallback）
  3. 都沒有 → 不發送，記錄錯誤

百大 / arena 類通知:
  1. ARENA_BOT_TOKEN
  2. 都沒有 → 不發送，記錄錯誤
  3. 禁止 fallback 到 TELEGRAM_BOT_TOKEN

董事會類通知:
  1. BOARD_BOT_TOKEN
  2. 都沒有 → 不發送，記錄錯誤
  3. 禁止 fallback 到 TELEGRAM_BOT_TOKEN
```

理由：TELEGRAM_BOT_TOKEN 現在是大腦 bot。專用 bot 缺 token 時若 fallback 到 TELEGRAM_BOT_TOKEN，會把百大或董事會訊息送進大腦，造成錯路由。

---

## 五、.env 變數對照

```
TELEGRAM_BOT_TOKEN=大腦bot的token  ← Hermes CLI 和通用通知用
HERMES_BOT_TOKEN=大腦bot的token    ← 與上面相同，相容舊碼
ARENA_BOT_TOKEN=百大bot的token     ← 競技場專用
BOARD_BOT_TOKEN=董事會bot的token   ← 董事會專用（如果有的話）
```

---

## 六、合規檢查清單

新增或修改任何發送端時，必須確認：
- [ ] 使用正確的 token 變數
- [ ] 專用 bot 路由缺 token 時必須 fail-closed，不得 fallback 到 TELEGRAM_BOT_TOKEN
- [ ] 不 hardcode bot token
- [ ] 不把競技場訊息發到大腦
- [ ] 不把治理訊息發到百大
- [ ] chat_id 正確（目前統一 6823341162）

---

*Bot Routing Standard v1.0 — 2026-05-05*
