# API 閘道與路由規範

| 項目 | 內容 |
|---|---|
| 適用範圍 | 所有 HTTP 流量:App/Web/鏡頭 → 後端,以及服務之間的 `/internal/*` 呼叫 |
| 架構決策 | `13_ADR_微服務與三節點部署.md` 第 1.2 節 |
| 設定檔 | `deploy/nginx/`,內容必須與本文件一致 |

## 1. 拓撲

Oracle Load Balancer 只決定請求送往 VM-1 或 VM-2;每台服務節點上的 Nginx 依路徑(必要時加上 HTTP method)把請求分派給七個服務之一。服務之間的內部呼叫同樣經過本機 Nginx。

```
                 App / Web / 鏡頭
                        │ HTTPS :443
                        ▼
              Oracle Flexible LB              TLS 在此終止
                 │ HTTP :23912  │ HTTP :23912
                 ▼              ▼
     ┌─ VM-1 ─────────────┐  ┌─ VM-2 ─────────────┐
     │ Nginx :23912 對外  │  │ Nginx :23912 對外  │
     │ Nginx :23919 內部  │  │ Nginx :23919 內部  │
     │ 七個服務 23921~23927│  │ 七個服務 23921~23927│
     └────────────────────┘  └────────────────────┘
               ▲     互為 backup(VCN 私有網路)     ▲
               └─────────────────┬────────────────┘
     ┌─ VM-3 ───────────────────────────────────────────┐
     │ Nginx :23919 內部                                 │
     │ worker :23931、Postgres :23951、Redis :23957       │
     │ RTSP 進流 :554、TURN :3478 / :443(中繼 49152~65535) │
     └──────────────────────────────────────────────────┘
```

| Listener | 綁定位址 | 允許來源 | 內容 |
|---|---|---|---|
| 對外 `:23912` | VM-1、VM-2 私有 IP | LB 子網路(OCI security list) | 第 3 節路由 |
| 內部 `:23919` | `127.0.0.1` | 同一台機器上的服務與 worker | 第 4 節路由 |

VM-3 只跑內部 listener,供事件偵測 / 轉碼 worker 呼叫 Push 與 Media。

## 2. Port 配置

本節是全系統 port 的唯一定義。

- **對公網開放的 port 一律使用協定標準 port**。理由:App、Web、鏡頭可能位於只放行標準 port 的網路(企業網路、飯店、Demo 現場 WiFi)。
- **僅 VCN 內部的 port 不使用協定或軟體的預設 port**(8080、5432、6379 等),號碼落在 23xxx,低於 Linux 動態 port 範圍(32768 起)。

所有容器以 host network(`network_mode: host`)執行,port 不經 NAT。

### 2.1 對公網開放

| 元件 | Port | 協定 | 所在 | 連線者 |
|---|---|---|---|---|
| Oracle LB listener(API) | 443 | TCP(HTTPS) | LB | App、Web、鏡頭 |
| Oracle LB listener(轉址) | 80 | TCP(HTTP) | LB | App、Web、鏡頭 |
| TURN listener | 3478 | UDP、TCP | VM-3 | App、Web、鏡頭 |
| TURN over TLS | 443 | TCP | VM-3 | App、Web、鏡頭 |
| TURN 中繼範圍 | 49152~65535 | UDP | VM-3 | App、Web、鏡頭 |
| RTSP 進流 | 554 | TCP | VM-3 | 鏡頭 |

- App、Web、鏡頭的 API base URL 皆為 `https://<API 網域>`。
- 80 由 LB 的 URL redirect rule 一律以 301 轉址到 443,不轉送到 Nginx。
- TURN 與 LB 使用不同的公網 IP,兩者的 443 互不衝突。Stream 核發給用戶端的 TURN `urls` 固定為以下三筆,用戶端的 ICE 同時嘗試並採用可連通者:`turn:<TURN 網域>:3478?transport=udp`、`turn:<TURN 網域>:3478?transport=tcp`、`turns:<TURN 網域>:443?transport=tcp`。
- Web 前端由 Cloudflare Pages 以標準 HTTPS 供應,不受此表影響;前端對 API 的請求為跨來源請求,CORS 允許清單列 Pages 網域。

### 2.2 僅 VCN 內部

| 元件 | Port | 所在 |
|---|---|---|
| Nginx 對外 listener(LB → Nginx) | 23912 | VM-1、VM-2 |
| Nginx 內部 listener | 23919(僅 `127.0.0.1`) | VM-1、VM-2、VM-3 |
| Auth | 23921 | VM-1、VM-2 |
| Device | 23922 | VM-1、VM-2 |
| Event(F3 時間軸 API) | 23923 | VM-1、VM-2 |
| Push | 23924 | VM-1、VM-2 |
| Media | 23925 | VM-1、VM-2 |
| Album | 23926 | VM-1、VM-2 |
| Stream 訊令 | 23927 | VM-1、VM-2 |
| 事件偵測 / 轉碼 worker | 23931 | VM-3 |
| Postgres | 23951 | VM-3 |
| Redis | 23957 | VM-3 |

- 服務、worker、Postgres、Redis 的 port 監聽私有 IP,OCI security list 只對 VCN CIDR 開放。
- `vm1.internal`、`vm2.internal`、`vm3.internal` 以 VCN private DNS zone 的 A 記錄解析到三台 VM 的固定私有 IP。Nginx 啟動時即解析 upstream 主機名稱,解析失敗則拒絕啟動。

## 3. 對外路由(`:23912`)

白名單制:只轉送下表路徑,其餘一律回 `GW_001`。新增公開端點必須同時更新本表與 `deploy/nginx/service-node/public.conf`。

| Method | Path | 服務 | 呼叫者 |
|---|---|---|---|
| * | `/auth/*` | Auth | App / Web |
| POST | `/devices/register` | Device | 鏡頭 |
| POST | `/devices/pair` | Device | App / Web |
| GET | `/devices` | Device | App / Web |
| PATCH、DELETE | `/devices/{device_id}` | Device | App / Web |
| POST | `/devices/{device_id}/heartbeat` | Device | 鏡頭 |
| GET | `/devices/{device_id}/events` | Event | App / Web |
| * | `/devices/{device_id}/stream/*` | Stream | App / Web |
| POST | `/devices/{device_id}/screenshot` | Media | App / Web |
| PATCH | `/events/{event_id}` | Event | App / Web |
| GET | `/events/{event_id}/playback-url` | Event | App / Web |
| POST | `/events/{event_id}/screenshot`、`/events/{event_id}/clip` | Media | App / Web |
| GET、PUT | `/push-tokens` | Push | App / Web |
| DELETE | `/push-tokens/{push_token_id}` | Push | App / Web |
| GET | `/media` | Album | App / Web |
| POST | `/media/export/google-drive` | Album | App / Web |
| GET | `/media/{media_item_id}` | **Media** | App / Web |
| DELETE | `/media/{media_item_id}` | **Album** | App / Web |
| * | `/integrations/google-drive/oauth-url`、`/integrations/google-drive/oauth-callback` | Album | App / Web |
| * | `/internal/devices/{device_id}/stream/pending-offer`、`/answer`、`/candidates` | Stream | 鏡頭 |
| GET | `/healthz` | Nginx 自身 | LB 健康檢查 |

路由規則:

- `/devices/...` 由 Device、Event、Stream、Media 四個服務共用,依子路徑以錨定的 regex 精確比對,不以前綴整批轉送。
- `/media/{media_item_id}` 依 method 分派:GET 送 Media,DELETE 送 Album。任一服務要在此路徑新增 method,須先更新本表。理由:`media_items` 由兩個服務共用(ADR 第 1 節),同一資源路徑的讀取與刪除分屬不同服務。
- 鏡頭 signaling(`06_spec_即時串流.md` 第 3.2 節)是 `/internal/*` 中唯一對外開放的路徑,以裝置憑證把關(`06_spec_即時串流.md` 第 3.3 節)。其餘 `/internal/*` 在對外 listener 一律回 `GW_001`。

## 4. 內部路由(`:23919`)

服務與 worker 呼叫其他服務時,base URL 一律為 `http://127.0.0.1:23919`。`X-Internal-Api-Key` 由被呼叫的服務驗證,Nginx 原樣轉送。

| Method | Path | 服務 | 呼叫者 | 定義於 |
|---|---|---|---|---|
| GET | `/internal/devices/{device_id}` | Device | Event、Push、Stream、Media | `04_spec_裝置管理.md` 第 3 節 |
| DELETE | `/internal/users/{user_id}/devices` | Device | Auth | `04_spec_裝置管理.md` 第 3 節 |
| DELETE | `/internal/devices/{device_id}/events` | Event | Device | `08_spec_時間軸與事件歷史.md` 第 3.3 節 |
| GET | `/internal/events/{event_id}` | Event | Media | Media 服務契約 `interfaces/backend/media/__init__.py` |
| POST | `/internal/notifications/event-ready` | Push | Event worker | `09_spec_推播通知.md` 第 3 節 |
| DELETE | `/internal/users/{user_id}/media` | Album | Auth | `12_spec_相簿與雲端匯出.md` 第 3 節 |
| POST | `/internal/media/{media_item_id}/ready`、`/failed` | Media | 轉碼 worker | Media 服務契約 `interfaces/backend/media/__init__.py` |
| POST | `/internal/frames`、`/internal/clips` | worker | Media | Media 服務契約 `interfaces/backend/media/__init__.py` |

未列出的路徑回 `GW_001`。

## 5. 容錯

**VM-1、VM-2**:每個服務的 upstream 以本機為主、另一台為 backup。

| 情境 | 行為 |
|---|---|
| 本機服務正常 | 只送本機 |
| 本機服務連線失敗或逾時 | 改送另一台;10 秒後重試本機(`max_fails=1 fail_timeout=10s`) |
| 整台 VM 故障 | LB 健康檢查(`/healthz`)移除該節點;該節點上的內部呼叫者隨之消失,不需另外處理 |

**VM-3**:upstream 同時列 `vm1.internal`、`vm2.internal`,輪流分派,被動剔除失敗節點。

**重送**:只在連線失敗或逾時時換下一台(`proxy_next_upstream error timeout`),最多 2 次。POST、PATCH 請求一旦送達上游即不重送;連線被拒(請求未送出)時可換 backup。

## 6. 用戶端 IP

`RATE_001` 對匿名端點以 IP 為限流 key(`10_錯誤處理與狀態規範.md` 第 3 節),服務必須取得真實用戶端 IP:

1. Nginx 以 `real_ip` 模組信任 LB 子網路送來的 `X-Forwarded-For`,還原用戶端 IP,再以 `proxy_set_header X-Forwarded-For $remote_addr` **覆寫**後轉送,丟棄用戶端自行偽造的值。
2. 服務以 uvicorn `--proxy-headers --forwarded-allow-ips=127.0.0.1,<VM-1 私有 IP>,<VM-2 私有 IP>` 啟動,`request.client.host` 即為真實 IP。

`--forwarded-allow-ips` 不得設為 `*`。理由:服務 port 對整個 VCN 開放,設為 `*` 時 VCN 內任何來源都能偽造 IP 繞過限流。

## 7. 逾時與請求大小

| 項目 | 值 |
|---|---|
| `proxy_connect_timeout` | 2 秒 |
| `proxy_read_timeout` | 60 秒(需大於鏡頭長輪詢 `pending-offer` 的 30 秒) |
| LB listener idle timeout | 60 秒以上 |
| `client_max_body_size` | 1 MB;影片與媒體檔走 R2 presigned URL,不經 Nginx |

## 8. Nginx 產生的錯誤

Nginx 自行產生的錯誤使用與服務相同的格式 `{"error": {"code": ..., "message": ...}}`:

| 情境 | HTTP | 錯誤碼 |
|---|---|---|
| 路徑不在第 3、4 節白名單 | 404 | `GW_001`(`10_錯誤處理與狀態規範.md` 第 3 節) |
| 上游全部連線失敗或逾時 | 503 | `SRV_002` |

服務自己回傳的錯誤(包含服務自身的 503)原樣轉送。

## 9. 服務端規範

- 各服務監聽第 2.2 節指定的 port;連線 Postgres、Redis 的 URL 使用第 2.2 節的 port。
- 呼叫其他服務或 worker 的 base URL 設定名稱為 `<服務名>_service_url`(worker 為 `worker_url`),預設值 `http://127.0.0.1:23919`。
- uvicorn 啟動參數依第 6 節設定。
- `X-Internal-Api-Key` 以 `hmac.compare_digest` 比對。
