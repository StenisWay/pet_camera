"""Auth 服務設定。

部署形狀見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md:服務複本跑在 VM-1/VM-2,
Postgres 與 Redis 是 VM-3 上的單例,透過 VCN 私有網路連線。

本服務是唯一持有 JWT 簽章密鑰**用於簽發**的服務(02_spec 第 2.8 節);
其餘六個服務拿同一把密鑰只做驗證。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AUTH_", extra="ignore")

    app_name: str = "Pet Camera Auth Service"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://auth@127.0.0.1:5432/pet_camera"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # 簽發與驗證共用同一把密鑰(02_spec 第 2.8 節)
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"

    # token 效期(02_spec 第 2.6 節的平台差異表)
    web_access_token_ttl_seconds: int = 60 * 60
    web_refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60
    app_access_token_ttl_seconds: int = 180 * 24 * 60 * 60
    app_token_extend_after_seconds: int = 7 * 24 * 60 * 60

    # 登入失敗鎖定(02_spec 第 2.3 節)
    max_login_attempts: int = 5
    lockout_seconds: int = 15 * 60

    # 忘記密碼(02_spec 第 2.4 節)
    password_reset_ttl_seconds: int = 30 * 60
    password_reset_url_template: str = "https://app.example.com/reset-password?token={token}"
    password_reset_max_per_hour: int = 5

    # 刪除帳號的跨服務串聯清除(05_spec 第 2.2 節),走 VCN 私有網路
    internal_api_key: str = "change-me-internal"
    device_service_base_url: str = "http://device.internal:8000"
    album_service_base_url: str = "http://album.internal:8000"
    internal_call_timeout_seconds: float = 10.0

    # 全站限流(10_錯誤處理與狀態規範.md,Redis 不可用時 fail-open)
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
