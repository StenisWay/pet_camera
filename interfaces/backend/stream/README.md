# Stream 訊令服務(F1:即時串流)

WebRTC 的 signaling 與 TURN 憑證簽發。對應規格書
`rule_doc/功能需求/06_spec_即時串流.md`(含第 9 節規格審查決議)。

**本服務不擁有任何 Postgres 資料表。** Session 是短效狀態,只存共用 Redis 並附 TTL。

```
app/
├── main.py                      composition root:adapter 在 lifespan 組好掛上 app.state
├── core/                        框架相關:config、http_errors、security、限流
├── shared_kernel/               純 Python:錯誤分類、Clock / IdGenerator
└── domains/streaming/
    ├── domain/                  StreamSession 聚合、DeviceSnapshot、TURN 憑證、repository 介面
    ├── application/             use case、DTO、對外界的 port
    ├── infrastructure/          Redis session / Pub/Sub、coturn 憑證、Device 服務 HTTP
    └── presentation/            觀看端 router、鏡頭端 internal_router、Pydantic schema
```

對外契約是 `__init__.py`(對應 domain 層),`tests/test_contract.py` 讓走樣當場紅燈。

## 執行

```bash
uv sync
uv run uvicorn app.main:app --port 8006

uv run pytest --cov=app --cov-report=term-missing
uv run pytest -m integration          # 需要真實 Redis(TEST_REDIS_URL 或 127.0.0.1:6379/15)
uv run python tools/check_layers.py --root .
uv run ruff check app tests && uv run mypy app
```

設定以 `STREAM_` 前綴的環境變數注入(見 `app/core/config.py`)。
`STREAM_TURN_STATIC_SECRET` 與 `STREAM_JWT_SECRET` 不進版控。

## 規格條目 ↔ 測試對照

| 規格 | 內容 | 測試 |
|---|---|---|
| 2.4 | session TTL 300 秒 | `domain/test_stream_session.py::test_expiry_boundary` |
| 2.4 | 同一擁有者直接接管,不回 STREAM_004 | `application/test_open_stream_session.py::test_second_session_takes_over_the_first`、`e2e/test_stream_flow.py::test_second_viewer_takes_over_and_the_first_is_cut_off` |
| 2.4 | 接管 = 單一 key 覆寫(last-writer-wins) | `contracts/test_stream_session_repository.py::test_saving_a_second_session_takes_over_the_device` |
| 2.3 | ICE 重連重送 offer,舊 answer 作廢 | `domain/test_stream_session.py::test_resubmitting_offer_restarts_negotiation` |
| 2.5 | coturn REST 認證(username / HMAC-SHA1 / 600s) | `infrastructure/test_turn.py` |
| 2.5 | 憑證效期長於 session TTL | `application/test_open_stream_session.py::test_turn_credentials_outlive_the_session` |
| 3.1 | 建立 session 回 201 + TURN 憑證 | `presentation/test_stream_routes.py::test_open_session_returns_201_with_turn_credentials` |
| 3.1 | offer 同步等 answer,逾時 5 秒 | `presentation/test_stream_routes.py::test_offer_times_out_with_408` |
| 3.1 | candidate 以 `since` 增量取回 | `domain/test_stream_session.py::test_candidates_are_returned_per_peer_and_incrementally`、`application/test_exchange_candidates.py` |
| 3.1 | DELETE 冪等,一律 204 | `application/test_end_stream_session.py`、`presentation/test_stream_routes.py::test_delete_session_is_204_and_idempotent` |
| 3.2 | 鏡頭端長輪詢 pending-offer,逾時回 204 | `presentation/test_internal_routes.py::test_long_poll_without_an_offer_is_204` |
| 3.2 | 鏡頭端回覆 answer / 交換 candidate | `presentation/test_internal_routes.py` |
| 3.3 | 擁有者驗證,查無與無權限同回 404 | `application/test_open_stream_session.py::test_other_users_device_looks_like_it_does_not_exist`、`test_signaling.py::test_offer_on_someone_elses_session_looks_like_a_missing_device` |
| 5 / 8 | 第二個觀看端接管,舊連線中斷 | `e2e/test_stream_flow.py::test_second_viewer_takes_over_and_the_first_is_cut_off` |
| 7 | STREAM_001 離線(status 或心跳超過 90 秒) | `domain/test_device_snapshot.py`、`application/test_open_stream_session.py::test_stale_heartbeat_counts_as_offline` |
| 7 | STREAM_002 = 401(session 失效/被接管) | `core/test_http_errors.py::test_session_expired_is_401_not_409` |
| 7 | STREAM_005 = 408(signaling 逾時) | `core/test_http_errors.py::test_signaling_timeout_is_408` |
| 7 | Redis 不可用 -> SRV_002;DELETE 例外 fail-open | `application/test_end_stream_session.py::test_store_outage_still_succeeds` |
| 審查 #10 | 建立 session 每人每分鐘 10 次 | `presentation/test_stream_routes.py::test_open_session_is_rate_limited` |
| 13_ADR 4 | Device 服務不可用時 fail-closed | `application/test_open_stream_session.py::test_device_service_outage_fails_closed` |
| 全站 | 錯誤回應形狀、VAL_001 = 400 | `core/test_http_errors.py`、`presentation/test_stream_routes.py::test_malformed_body_is_400` |

## 採用的假設

- **限流只掛在 `POST .../stream/session`。** 審查 #10 說的是「建立 session 是昂貴操作」;
  offer 與 candidate 是 ICE 協商期間的高頻往返,套同一個「每分鐘 10 次」會把正常連線擋掉。
- **通知不是真相。** Redis Pub/Sub 不補送,訊息在訂閱之前發布就遺失。因此 `submit_offer`
  與 `fetch_pending_offer` 在等待結束後(不論收到通知還是逾時)一律重讀一次 Redis。
- **`session_id` 與路徑上的 `device_id` 必須一致。** 規格只說要驗擁有者;不一起驗裝置的話,
  同一位使用者可以拿 A 鏡頭的 session 去推進 B 鏡頭的 signaling。
- **一次送出的 candidate 上限 50 筆、SDP 上限 64 KB。** 規格未規定。candidate 會整包寫回
  Redis,沒有上限等於讓任何持有 session 的人把 key 撐到記憶體用盡。
- **鏡頭端憑證走 `X-Device-Credential` 標頭。** 機制未定,先用可替換的介面(見下)。

## 已知限制與待辦

1. 🔴 **Device 服務的 `DeviceSummary` 沒有 `last_seen_at`。**
   審查 #7 決議由 Stream 自己檢查心跳新鮮度,否則 `STREAM_001` 永遠不會觸發
   (沒有人把 `paired` 轉成 `offline`)。但 `interfaces/backend/device/__init__.py` 的
   `DeviceSummary` 只有 `id / name / user_id / status`。
   **目前行為**:沒有 `last_seen_at` 的回應一律判為離線(fail-closed,13_ADR 第 4 節)。
   在欄位補上之前,**任何直播都會被擋在 STREAM_001**。
   需要 Device 服務在 `DeviceSummary` 加上 `last_seen_at`,並把 Stream 加進
   `/internal/devices/{device_id}` 的呼叫者清單。
   對應測試:`infrastructure/test_device_directory.py::test_missing_last_seen_at_is_treated_as_never_reported`。

2. 🟡 **鏡頭端認證機制尚未定案**(06_spec 第 9 節待確認事項)。
   目前是 `SharedSecretCameraAuthenticator`——只驗共享金鑰,**無法區分是哪一支鏡頭**,
   拿到金鑰的任一鏡頭都能冒充其他鏡頭。Device 服務決定機制(裝置 token / mTLS)後
   換掉 `CameraAuthenticator` 的實作即可,其餘各層不受影響。
   對應測試:`core/test_security.py::test_shared_secret_cannot_tell_cameras_apart`
   (這則測試把限制寫下來;換成逐裝置憑證後它應該要失敗)。

3. 🟡 **Redis 實作尚未跑過真實 Redis。** `redis_session_repository.py` 與
   `redis_signaling.py` 的合約測試已經寫好並標記 `integration`,但本機沒有 Redis
   也沒有 Docker,無法執行。有 Redis 的環境請跑
   `uv run pytest -m integration`——這兩支是目前唯一沒有實際驗證過的程式碼。

4. 🟡 **NFR「首幀出現時間 < 3 秒」無法在後端驗證**(第 9 節)。
   本服務可被測的承諾是 `POST .../stream/session` 的 P95 < 200ms,需要負載測試,
   不在單元測試範圍。首幀 3 秒留給前端 E2E 驗收。

5. 🟢 **`STREAM_004` 現階段不會被觸發**(第 2.4 節),保留給未來「鏡頭共享給多位使用者」。
   程式裡沒有對應的例外類別,等該功能實作時再加。

## 覆蓋率

`domain` / `application` / `presentation` 皆 100%。未覆蓋的是:

| 檔案 | 原因 |
|---|---|
| `infrastructure/redis_session_repository.py`、`redis_signaling.py` | 需要真實 Redis,由 `-m integration` 的合約測試覆蓋(見待辦 3) |
| `core/redis_rate_limit.py` | 同上;fail-open 的判斷在 `core/rate_limit.py`,已 100% |
| `main.py` 的 `build_adapters` / `lifespan` | composition root,連線真實 Redis 與 Device 服務 |

## 建議的下一步

1. 把待辦 1 送回 Device 服務與 `rule_doc`(`03_spec_裝置配對.md` / `04_spec_裝置管理.md`
   的 `DeviceSummary`),這是唯一會讓功能完全不能用的缺口。
2. 在有 Redis 的環境跑 `uv run pytest -m integration`。
3. 待 Device 服務定出鏡頭認證機制後,換掉 `SharedSecretCameraAuthenticator`。
4. TURN server(coturn)的部署與 `static-auth-secret` 佈署到 VM-3。
