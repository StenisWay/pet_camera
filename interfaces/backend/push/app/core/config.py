"""Push 服務設定。

部署形狀見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md:服務複本跑在 VM-1/VM-2,
Postgres 與 Redis 是 VM-3 上的單例,透過 VCN 私有網路連線。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PUSH_", extra="ignore")

    app_name: str = "Pet Camera Push Service"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://push@127.0.0.1:5432/pet_camera"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # 與 Auth 服務共用的 JWT 簽章設定(Push 只驗證,不簽發)
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"

    # 跨服務內部端點(09_spec 第 3 節):本服務對外把關用,以及呼叫 Device 服務時夾帶
    internal_api_key: str = "change-me-internal"
    device_service_base_url: str = "http://device.internal:8002"

    r2_endpoint_url: str = ""
    r2_bucket: str = "pet-camera"
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    # 09_spec 第 2.2 節(審查 #6):通知夾帶的縮圖效期 30 分鐘,不是點播時的 10 分鐘
    thumbnail_url_ttl_seconds: int = 30 * 60

    # 09_spec 第 2.3 節:防洗版計數窗
    dedup_window_seconds: int = 5 * 60
    # 13_ADR 第 4 節:發送路徑查詢失敗時延後重試(秒),用盡才放棄。總長遠小於
    # 驗收標準的「10 秒內收到通知」並不衝突——重試只發生在 VM-3 或 Device 暫時失聯時
    lookup_retry_delays_seconds: tuple[float, ...] = (1, 3, 5)
    device_service_timeout_seconds: float = 3.0
    push_provider_timeout_seconds: float = 10.0

    # 推播通道憑證(尚未備妥,adapter 留空殼,見 README 的「已知限制」)
    fcm_credentials_json: str = ""
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_private_key: str = ""
    web_push_vapid_public_key: str = ""
    web_push_vapid_private_key: str = ""

    # 09_spec 第 3 節(審查 #16):PUT /push-tokens 每使用者每分鐘 10 次
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60

    # deep link(09_spec 第 2.2 節、screens/app/02、screens/web/02):點擊通知後開攝影機畫面,
    # 首發通知另帶 ?event_id= 讓畫面直接播放該事件
    deep_link_base: str = "petcamera://devices"
    web_base_url: str = "https://petcamera.example.com"
    # FCM HTTP v1 需要專案 ID;APNs 經由 FCM 轉送(iOS 的 App 也向 FCM 取 registration token)
    fcm_project_id: str = ""
    web_push_vapid_subject: str = "mailto:ops@petcamera.example.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
