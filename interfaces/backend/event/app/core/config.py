"""Event 服務設定。

部署形狀見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md:F3 的時間軸 API 以複本形式
跑在 VM-1/VM-2,F2 的偵測 worker 是 VM-3 上的單例(與 Postgres 同機,寫入不跨網路)。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="EVENT_", extra="ignore")

    app_name: str = "Pet Camera Event Service"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://event@127.0.0.1:5432/pet_camera"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # 與 Auth 服務共用的 JWT 簽章設定(Event 只驗證,不簽發)
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"

    r2_endpoint_url: str = ""
    r2_bucket: str = "pet-camera"
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""

    # 跨服務內部呼叫(08_spec 第 3.2、3.3 節)。同一把金鑰既用於驗證打進來的請求,
    # 也用於本服務打出去的請求——七個服務都在同一個 VCN 私有網路內。
    internal_api_key: str = "change-me-internal"
    device_service_url: str = "http://device:8002"
    push_service_url: str = "http://push:8004"

    # 08_spec 第 2.1 節
    timeline_page_size: int = 20
    timeline_max_page_size: int = 100
    default_timezone: str = "Asia/Taipei"
    presigned_url_ttl_seconds: int = 600

    # 07_spec 第 2 節的錄影規則。門檻可調(規格寫「預設 0.6」),其餘是硬性上限。
    motion_threshold: str = "0.60"
    silence_timeout_seconds: int = 5
    max_recording_seconds: int = 60
    upload_max_attempts: int = 3

    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
