"""Album 服務設定。

部署形狀見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md:服務複本跑在 VM-1/VM-2,
Postgres 與 Redis 是 VM-3 上的單例,透過 VCN 私有網路連線。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ALBUM_", extra="ignore")

    app_name: str = "Pet Camera Album Service"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://album@127.0.0.1:5432/pet_camera"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # 與 Auth 服務共用的 JWT 簽章設定(Album 只驗證,不簽發)
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"

    r2_endpoint_url: str = ""
    r2_bucket: str = "pet-camera"
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "https://app.example.com/integrations/google-drive/callback"
    drive_folder_name: str = "寵物攝影機"

    internal_api_key: str = "change-me-internal"

    # 相簿依日期分組/篩選的時區(12_spec 第 2.1 節)。資料仍以 UTC 儲存。
    timezone: str = "Asia/Taipei"
    page_size: int = 30
    max_page_size: int = 100
    export_batch_limit: int = 50
    export_stale_after_seconds: int = 15 * 60
    presigned_url_ttl_seconds: int = 600

    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
