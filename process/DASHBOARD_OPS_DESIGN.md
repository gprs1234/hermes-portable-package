# Dashboard → 操作面板設計

日期: 2026-05-05
狀態: design only

---

## 一、現狀

Governance Dashboard 目前是純只讀：
- HTML + MD 報告
- 25 個 section
- 不接受操作指令

## 二、目標

讓 Dashboard 變成可操作的面板（但仍需多層確認）。

## 三、操作清單（候選）

| 操作 | 風險 | 確認層級 | 狀態 |
|------|------|----------|------|
| 查看 PLAN 詳情 | LOW | 無需確認 | 已有 |
| 觸發 PLAN 心跳檢查 | LOW | 1 層確認 | 可做 |
| 重新產生 Dashboard | LOW | 1 層確認 | 可做 |
| 啟動/停止服務 | HIGH | 董事會+confirm | 未開放 |
| 修改 PLAN status | HIGH | 董事會+confirm | 未開放 |
| 重啟 bot | MEDIUM | 2 層確認 | 未開放 |

## 四、實作方式

### 方案 A: CLI 指令（推薦）
```
hermes dashboard refresh          # 重建 HTML
hermes dashboard check <plan_id>  # 觸發心跳檢查
hermes dashboard approve <event>  # 批准待處理事項
```

### 方案 B: HTML 互動按鈕
- Dashboard HTML 加入表單
- POST 到本地 API
- 風險較高（需 CSRF 保護）

### 方案 C: TG 指令
- 從 TG 發 /dashboard 指令
- 走 MGL 通道
- 與現有 governance loop 整合

**建議: 先做 A（CLI），再做 C（TG），不做 B（HTML 表單）**

## 五、安全規則

- 所有操作必須經過至少一層確認
- 啟動/停止服務需要董事會 + Nomi final_confirm
- 操作結果必須寫入 audit trail
- 不得繞過 Gateway 事件系統

---

*Dashboard 操作面板設計 v1.0*
