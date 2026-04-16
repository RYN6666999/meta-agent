# crm-esmodule-refactor

- timestamp: 2026-04-17 00:20:50
- summary: crm.js 5062行拆分為 src/ ES Module 樹，navigate()修復，日報/業績完整移植
- root_cause: navigate()用.page-section選器(HTML用.page)、CSS class切換敵不過#page-crm ID規則、.nav-item[data-page]選器不存在(HTML用.tab-btn+onclick)；日報/業績renderPage未渫染表單HTML
- fix: 改用el.style.display inline style、.tab-btn[onclick*='page']選器、canvas/calendar alias正規化；日報兩欄完整移植18格時間安排+三件大事+復盤；業績kpi-bar+prod-grid+7欄成交表
- verify: PR#2建立，preview server視覺確認，28/28 guard tests pass
