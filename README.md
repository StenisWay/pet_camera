# 寵物攝影機系統 (Pet Camera System)

飼主外出時也能掌握寵物在家狀況的智慧寵物攝影機。提供即時畫面查看、寵物活動自動偵測錄影、推播通知與事件時間軸回顧，讓使用者不用一直盯著直播畫面也能掌握寵物動態。

> 目前專案階段:**設計/規劃期** — 需求、規格、資料模型與介面合約皆已完成，正在進行 UI 設計(Figma)與硬體採購。

---

## 功能總覽 (MVP)

| # | 功能 | 優先級 |
|---|---|---|
| F0.1 | 登入註冊與密碼重設 | P0 |
| F0.2 | 裝置配對 | P0 |
| F0.3 | 裝置管理 | P0 |
| F0.4 | 帳號設定 | P1 |
| F1 | 即時串流 (WebRTC/TURN) | P0 |
| F2 | 事件偵測與自動錄影 | P0 |
| F3 | 時間軸 / 事件歷史瀏覽 | P0 |
| F4 | 推播通知 | P1 |
| F5 | 剪輯與截圖 | P1 |
| F6 | 相簿與 Google Drive 匯出 | P1 |

**範圍外 (Phase 2+)**:雙向語音對講、多人共享鏡頭、多鏡頭 grid 檢視、AI 寵物辨識、訂閱制收費、自動餵食器。

## 技術架構

| 層級 | 技術 |
|---|---|
| Web 前端 | TypeScript (CSR)，託管於 Cloudflare Pages |
| iOS App | Swift (原生) |
| Android App | Kotlin (原生) |
| 後端 | Python + Pydantic，7 個微服務 (Auth / Device / Event / Stream / Push / Media / Album) |
| 資料庫 | PostgreSQL (僅存 metadata)，Redis (短效共享狀態) |
| 物件儲存 | Cloudflare R2 (影片、縮圖、媒體檔) |
| 影音串流 | RTSP 進流 (MediaMTX) + WebRTC/TURN 出流 |
| 硬體 | Raspberry Pi 5 (開發) / Pi Zero 2 W (量產目標)，Camera Module 3 |
| 部署 | Oracle Always Free (3 VMs) + Oracle Flexible Load Balancer |

架構採**三節點 + Load Balancer** 拓撲:VM-1/VM-2 跑無狀態服務複本、VM-3 集中 Postgres、Redis、事件偵測 worker、TURN 四個單例元件。詳細決策理由見 [13_ADR_微服務與三節點部署.md](rule_doc/功能需求/13_ADR_微服務與三節點部署.md)。

## 專案結構

```
pet_camera/
├── interfaces/                 # 跨平台倉儲介面合約(先行定義,尚未實作)
│   ├── backend/                # Python (Pydantic) repository protocols
│   ├── web/                    # TypeScript repository interfaces
│   ├── android/                # Kotlin repository interfaces
│   └── ios/                    # Swift repository protocols
├── hardware/                   # 硬體規格書、開發流程圖、元件裝設位置圖
├── rule_doc/
│   ├── 99_SDLC矩陣圖.md         # 功能 × SDLC 產出追蹤矩陣
│   └── 功能需求/
│       ├── 00_PRD_需求書.md      # 產品需求書
│       ├── 01_資料模型與儲存規格.md
│       ├── 02~13_spec_*.md      # 各功能規格書 + 錯誤處理規範 + ADR
│       ├── diagrams/            # draw.io 架構/ER/流程圖
│       └── screens/
│           ├── app/             # App 畫面規格 (6 頁)
│           └── web/             # Web 畫面規格 (6 頁)
└── .claude/skills/             # 文件產生輔助 skill (draw.io/ER/規格書等)
```

## 開發進度

| SDLC 階段 | 狀態 | 產出 |
|---|---|---|
| 需求 (PRD) | ✅ 完成 | `00_PRD_需求書.md` |
| 功能規格 | ✅ 完成 | 11 份功能規格書 (`02~12_spec_*.md`) |
| 資料模型 | ✅ 完成 | `01_資料模型與儲存規格.md` (7 張資料表 + R2) |
| 畫面規格 | ✅ 完成 | App / Web 各 6 頁畫面規格書 |
| 系統設計 | ✅ 完成 | 12 張流程圖、ER 圖、架構圖、ADR (`13_ADR_*.md`) |
| 硬體規格 | ✅ 完成 | `硬體規格書.md` + 元件裝設位置圖 + 硬體開發流程圖 |
| 介面合約 | ✅ 完成 | 7 個後端服務與 App/Web 的 repository 介面定義 |
| **UI 設計 (Figma)** | 🔄 **進行中** | 依 `screens/` 畫面規格繪製設計稿 |
| **硬體採購** | 🔄 **進行中** | 依 `hardware/硬體規格書.md` 採購 |
| 實作 | ⏳ 未開始 | 各平台 repository 介面已就緒,可立即開發 |
| 測試 | ⏳ 未開始 | - |
| 部署 | ⏳ 未開始 | - |

進度細節對照:[99_SDLC矩陣圖.md](rule_doc/99_SDLC矩陣圖.md)。

## 快速開始

目前專案尚未進入實作階段，尚無可執行的應用程式。介面合約位於 `interfaces/`，作為未來各平台實作時的唯一資料來源。

## 文件導覽

- [產品需求書 (PRD)](rule_doc/功能需求/00_PRD_需求書.md) — 產品目標、MVP 範圍、系統架構
- [資料模型與儲存規格](rule_doc/功能需求/01_資料模型與儲存規格.md)
- [系統架構圖](rule_doc/功能需求/diagrams/00_architecture_系統架構圖.drawio) — 需用 [diagrams.net](https://app.diagrams.net) 開啟
- [硬體規格書](hardware/硬體規格書.md)
- [SDLC 矩陣圖](rule_doc/99_SDLC矩陣圖.md) — 各功能在各階段的產出總索引