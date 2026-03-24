# CRM-status-pill-click-無法切換

- timestamp: 2026-03-24 19:46:38
- summary: status-pill 點擊無法循環切換狀態（高意願/觀察中/冷淡/無效）
- root_cause: wrap.setPointerCapture(e.pointerId) 導致 click 事件的 e.target 被重定向到 wrap，composedPath 只往上查祖先不查子元素，永遠找不到 status-pill，事件委派靜默失敗
- fix: 1. 移除 setPointerCapture 2. status-pill 改用 inline onclick 直接綁定 3. cycleStatus 改用 targeted DOM update 取代 renderNodes()
- verify: v=10 debug log 確認 onclick 觸發、cycleStatus 正常執行，用戶確認修復
