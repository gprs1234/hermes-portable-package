# TG↔CLI 自動同步設計

日期: 2026-05-05
狀態: design only

---

## 一、現狀

- TG UPDATE_CONTEXT 不會自動同步到 CLI 的 active_context.md
- 需要人工在 CLI 端手動確認落地
- 已知 gap: TG_CLI_CONTEXT_SYNC_GAP.md

## 二、目標

建立自動同步通道：TG 上的重要決策/狀態自動進入 CLI 端的記憶系統。

## 三、設計

### 資料流
```
TG 用戶發訊息
  → hermes_bot.py 收到
  → chat_history 更新
  → tg_request_detector 掃描
  → 如果是 UPDATE_CONTEXT 類型:
    → context_update_detector 偵測
    → 產 context_update event
    → CLI review (自動或人工)
    → 寫入 active_context.md
    → audit log
```

### 同步條件（自動放行）

只同步以下類型：
- 用戶明確說「記住這個」
- 用戶確認的事實（Verified Fact）
- 決策結果（Decision）

不同步：
- 一般對話
- 問句
- 推測/假設
- 未經驗證的資訊

### 安全規則

- 自動同步的內容必須標記 `auto_synced: true`
- 來源必須標記 `source: tg_hermes_agent`
- 如果 CLI 端有衝突（同 key 不同 value），以 CLI 為準
- 每次同步產生 audit log
- 不同步 token/secret/敏感資訊

## 四、實作順序

Phase CS5: Design（本文件）
Phase CS6: 自動分類器（判斷哪些 TG 訊息值得同步）
Phase CS7: 自動 apply（低風險內容直接落地）
Phase CS8: Dashboard 顯示 sync 狀態

## 五、風險

- 低：只寫 active_context.md，可 rollback
- 中：自動同步可能寫入錯誤資訊（需標記來源）
- 低：衝突處理（CLI 端優先）

---

*TG↔CLI 自動同步設計 v1.0*
