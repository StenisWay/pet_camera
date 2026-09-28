"""Media 服務設定。

部署形狀見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md:服務複本跑在 VM-1/VM-2,
Postgres、Redis 與**事件偵測/轉碼 worker** 都是 VM-3 上的單例,透過 VCN 私有網路連線。
擷幀與剪輯轉碼都發生在 worker 上(規格審查 #2、#3),本服務只負責業務規則與紀錄。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MEDIA_", extra="ignore")

    app_name: str = "Pet Camera Media Service"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://media@127.0.0.1:5432/pet_camera"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # 與 Auth 服務共用的 JWT 簽章設定(Media 只驗證,不簽發)
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"

    r2_endpoint_url: str = ""
    r2_bucket: str = "pet-camera"
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""

    # 跨服務呼叫,一律走 VCN 私有網路、不經 Load Balancer(13_ADR 第 1 節)
    internal_api_key: str = "change-me-internal"
    event_service_url: str = "http://vm1.internal:8003"
    device_service_url: str = "http://vm1.internal:8002"
    worker_url: str = "http://vm3.internal:9000"

    # 11_spec 第 2.2 節 + 規格審查 #4:上限對齊 F2 的單一事件錄影上限 60 秒
    max_clip_seconds: int = 60
    # 資料模型第 3.2 節:videos/ 的 lifecycle rule 是 7 天(規格審查 #8 以此推算)
    video_retention_days: int = 7
    # 規格審查 #9:processing 停留超過 15 分鐘改判 failed,與 F6 的 exporting 對稱
    processing_stale_after_seconds: int = 15 * 60
    presigned_url_ttl_seconds: int = 600

    # 規格審查 #15:擷幀與轉碼吃的是 VM-3 的 2 OCPU,全系統瓶頸
    screenshot_rate_limit: int = 10
    clip_rate_limit: int = 3
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
