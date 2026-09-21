# SDLC 矩陣圖

各功能在軟體開發生命週期(SDLC)各階段的產出對照表。已完成的產出附連結;尚未開始的階段僅標示狀態,不附連結。畫面規格依平台分開維護(App/Web 版面配置與導覽不同),「畫面規格」欄位分別列出兩個平台的連結。

| # | 功能 | 需求 | 功能規格 | 畫面規格(App) | 畫面規格(Web) | 資料模型 | UML 流程圖 | 實作 | 測試 | 部署 |
|---|---|---|---|---|---|---|---|---|---|---|
| F0.1 | 登入註冊與密碼重設 | [00_PRD_需求書](功能需求/00_PRD_需求書.md) | [02_spec_登入註冊與密碼重設](功能需求/02_spec_登入註冊與密碼重設.md) | [app/01_page_登入註冊忘記密碼](功能需求/screens/app/01_page_登入註冊忘記密碼.md) | [web/01_page_登入註冊忘記密碼](功能需求/screens/web/01_page_登入註冊忘記密碼.md) | [01_資料模型與儲存規格](功能需求/01_資料模型與儲存規格.md)(`users`、`refresh_tokens`、`oauth_identities`) | [diagrams/02_flow_登入註冊與密碼重設.drawio](功能需求/diagrams/02_flow_登入註冊與密碼重設.drawio) | 未開始 | 未開始 | 未開始 |
| F0.2 | 裝置配對 | [00_PRD_需求書](功能需求/00_PRD_需求書.md) | [03_spec_裝置配對](功能需求/03_spec_裝置配對.md) | [app/03_page_首頁](功能需求/screens/app/03_page_首頁.md)(新增裝置入口) | [web/03_page_首頁](功能需求/screens/web/03_page_首頁.md)(新增裝置入口) | [01_資料模型與儲存規格](功能需求/01_資料模型與儲存規格.md)(`devices`) | [diagrams/03_flow_裝置配對.drawio](功能需求/diagrams/03_flow_裝置配對.drawio) | 未開始 | 未開始 | 未開始 |
| F0.3 | 裝置管理 | [00_PRD_需求書](功能需求/00_PRD_需求書.md) | [04_spec_裝置管理](功能需求/04_spec_裝置管理.md) | [app/06_page_會員資料](功能需求/screens/app/06_page_會員資料.md)(裝置管理入口) | [web/06_page_會員資料](功能需求/screens/web/06_page_會員資料.md)(裝置管理入口) | [01_資料模型與儲存規格](功能需求/01_資料模型與儲存規格.md)(`devices`) | [diagrams/04_flow_裝置管理.drawio](功能需求/diagrams/04_flow_裝置管理.drawio) | 未開始 | 未開始 | 未開始 |
| F0.4 | 帳號設定 | [00_PRD_需求書](功能需求/00_PRD_需求書.md) | [05_spec_帳號設定](功能需求/05_spec_帳號設定.md) | [app/06_page_會員資料](功能需求/screens/app/06_page_會員資料.md)(修改密碼/刪除帳號,無登出) | [web/06_page_會員資料](功能需求/screens/web/06_page_會員資料.md)(修改密碼/刪除帳號/登出) | [01_資料模型與儲存規格](功能需求/01_資料模型與儲存規格.md)(`users`、`oauth_identities`) | [diagrams/05_flow_帳號設定.drawio](功能需求/diagrams/05_flow_帳號設定.drawio) | 未開始 | 未開始 | 未開始 |
| F1 | 即時串流 | [00_PRD_需求書](功能需求/00_PRD_需求書.md) | [06_spec_即時串流](功能需求/06_spec_即時串流.md) | [app/04_page_攝影機畫面](功能需求/screens/app/04_page_攝影機畫面.md)(即時/歷史分頁切換) | [web/04_page_攝影機畫面](功能需求/screens/web/04_page_攝影機畫面.md)(主欄即時畫面) | - | [diagrams/06_flow_即時串流.drawio](功能需求/diagrams/06_flow_即時串流.drawio) | 未開始 | 未開始 | 未開始 |
| F2 | 事件偵測與自動錄影 | [00_PRD_需求書](功能需求/00_PRD_需求書.md) | [07_spec_事件偵測與自動錄影](功能需求/07_spec_事件偵測與自動錄影.md) | [app/04_page_攝影機畫面](功能需求/screens/app/04_page_攝影機畫面.md)(歷史分頁呈現處) | [web/04_page_攝影機畫面](功能需求/screens/web/04_page_攝影機畫面.md)(側欄呈現處) | [01_資料模型與儲存規格](功能需求/01_資料模型與儲存規格.md)(`events`) | [diagrams/07_flow_事件偵測與自動錄影.drawio](功能需求/diagrams/07_flow_事件偵測與自動錄影.drawio) | 未開始 | 未開始 | 未開始 |
| F3 | 時間軸與事件歷史 | [00_PRD_需求書](功能需求/00_PRD_需求書.md) | [08_spec_時間軸與事件歷史](功能需求/08_spec_時間軸與事件歷史.md) | [app/04_page_攝影機畫面](功能需求/screens/app/04_page_攝影機畫面.md)(歷史分頁) | [web/04_page_攝影機畫面](功能需求/screens/web/04_page_攝影機畫面.md)(側欄歷史列表) | [01_資料模型與儲存規格](功能需求/01_資料模型與儲存規格.md)(`events`) | [diagrams/08_flow_時間軸與事件歷史.drawio](功能需求/diagrams/08_flow_時間軸與事件歷史.drawio) | 未開始 | 未開始 | 未開始 |
| F4 | 推播通知 | [00_PRD_需求書](功能需求/00_PRD_需求書.md) | [09_spec_推播通知](功能需求/09_spec_推播通知.md) | [app/06_page_會員資料](功能需求/screens/app/06_page_會員資料.md)(通知設定入口) | [web/06_page_會員資料](功能需求/screens/web/06_page_會員資料.md)(通知設定入口) | - | [diagrams/09_flow_推播通知.drawio](功能需求/diagrams/09_flow_推播通知.drawio) | 未開始 | 未開始 | 未開始 |
| F5 | 剪輯與截圖 | [00_PRD_需求書](功能需求/00_PRD_需求書.md) | [11_spec_剪輯與截圖](功能需求/11_spec_剪輯與截圖.md) | [app/04_page_攝影機畫面](功能需求/screens/app/04_page_攝影機畫面.md)(操作列) | [web/04_page_攝影機畫面](功能需求/screens/web/04_page_攝影機畫面.md)(主欄操作列) | [01_資料模型與儲存規格](功能需求/01_資料模型與儲存規格.md)(`media_items`) | [diagrams/11_flow_剪輯與截圖.drawio](功能需求/diagrams/11_flow_剪輯與截圖.drawio) | 未開始 | 未開始 | 未開始 |
| F6 | 相簿與 Google Drive 匯出 | [00_PRD_需求書](功能需求/00_PRD_需求書.md) | [12_spec_相簿與雲端匯出](功能需求/12_spec_相簿與雲端匯出.md) | [app/05_page_相簿](功能需求/screens/app/05_page_相簿.md) | [web/05_page_相簿](功能需求/screens/web/05_page_相簿.md) | [01_資料模型與儲存規格](功能需求/01_資料模型與儲存規格.md)(`media_items`、`google_drive_credentials`) | [diagrams/12_flow_相簿與雲端匯出.drawio](功能需求/diagrams/12_flow_相簿與雲端匯出.drawio) | 已完成(`feat/album-service` 分支) | 已完成(同分支,197 項) | 未開始 |

## 說明

- 所有功能需求文件(PRD、功能規格書、畫面規格書、共用規範、流程圖)都放在 `功能需求/` 子資料夾,本檔案是唯一留在 `rule_doc/` 最外層的文件,作為整體索引。
- 畫面規格依平台分成 `功能需求/screens/app/` 與 `功能需求/screens/web/` 兩組,檔名相同、內容各自描述該平台的版面配置與導覽(如 App 底部 Tab bar vs Web 頂部導覽列、App 分頁切換即時/歷史 vs Web 雙欄同時顯示)。
- 「需求」「功能規格」「資料模型」「UML 流程圖」欄位皆已完成,連結指向對應文件;F1、F4 不涉及專屬資料表,標示「-」。
- 「實作」「測試」「部署」欄位一律只在產出**可從本檔連到**時才附連結。F6 的實作與測試已完成,但程式在 `feat/album-service` 分支上,main 的工作目錄沒有這些檔案,因此只標狀態不附連結;待該分支併入 main(或開出 PR)後再補連結。其餘功能的實作/測試狀態未經確認,維持原樣。
- F6 的資料模型多了 `google_drive_credentials`(Album 服務擁有的 Google Drive 授權憑證,見 [功能需求/01_資料模型與儲存規格.md](功能需求/01_資料模型與儲存規格.md) 第 2.8 節),對應的 migration 是 `db/migrations/versions/0003_album_google_drive_credentials.py`。
- 共用的橫向規範(不屬於單一功能列,故不列在表中):`功能需求/10_錯誤處理與狀態規範.md`(錯誤碼/UI 狀態規則)、`功能需求/14_API閘道與路由規範.md`(Nginx 閘道路由表、port 配置、服務間呼叫路徑,設定檔在 [`deploy/nginx/`](../deploy/nginx/README.md))、`功能需求/screens/app/02_page_導覽與全域結構.md`、`功能需求/screens/web/02_page_導覽與全域結構.md`(全域導覽結構,App/Web 分開維護)。
- 系統架構圖(整體元件與部署關聯,對應 PRD 第 5 節,三節點 + Load Balancer 拓撲:VM-1/VM-2 跑無狀態服務複本、VM-3 集中四個單例元件 Postgres/Redis/事件偵測 worker/TURN;含 OCI(含 VCN 子網路)/Cloudflare 與第三方服務雲端邊界,外部連線直連 VM 不經 LB):[功能需求/diagrams/00_architecture_系統架構圖.drawio](功能需求/diagrams/00_architecture_系統架構圖.drawio),決策理由見 [功能需求/13_ADR_微服務與三節點部署.md](功能需求/13_ADR_微服務與三節點部署.md)。
- 資料庫 ER 圖(整體資料表關聯,非單一功能流程):[功能需求/diagrams/01_er_資料模型.drawio](功能需求/diagrams/01_er_資料模型.drawio),欄位、nullable 與 `ON DELETE` 行為以 [功能需求/01_資料模型與儲存規格.md](功能需求/01_資料模型與儲存規格.md) 第 2 節為準。
- schema 的可執行版本(SQLAlchemy model + Alembic migration + 本地建置腳本)在 [`db/`](../db/README.md);它不隸屬任一功能列,七個服務共用同一個資料庫。改 schema 一律走 `db/migrations/`,並同步更新上述規格書與 ER 圖。
- UML 流程圖、ER 圖、系統架構圖皆為 draw.io(`.drawio`)格式,需以 [diagrams.net](https://app.diagrams.net) 或安裝 draw.io 應用程式開啟編輯。
