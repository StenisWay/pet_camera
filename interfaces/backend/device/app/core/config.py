"""Device 服務設定。

部署形狀見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md:服務複本跑在 VM-1/VM-2,
Postgres 與 Redis 是 VM-3 上的單例,透過 VCN 私有網路連線。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DEVICE_", extra="ignore")

    app_name: str = "Pet Camera Device Service"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://device@127.0.0.1:5432/pet_camera"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # 與 Auth 服務共用的 JWT 簽章設定(Device 只驗證,不簽發)
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"

    # 服務之間的內部端點共用金鑰(規格審查 #7、#8)
    internal_api_key: str = "change-me-internal"

    # Event 服務的內部端點:移除裝置時清除該裝置的事件與 R2 物件(規格審查 #7)
    event_service_base_url: str = "http://event:8000"
    event_cleanup_timeout_seconds: float = 10.0

    # 03_spec 第 2.1 節:配對碼有效期 10 分鐘
    pairing_code_ttl_seconds: int = 10 * 60
    # 規格審查 #4:8 碼 Crockford Base32
    pairing_code_length: int = 8
    # 產碼碰撞時的重試次數(部分唯一索引 pairing_code where not null)
    pairing_code_max_attempts: int = 3

    # 03_spec 第 2.3 節:心跳每 30 秒,超過 90 秒視為離線
    heartbeat_interval_seconds: int = 30
    offline_after_seconds: int = 90

    # 規格審查 #13:每帳號配對上限
    max_devices_per_user: int = 20
    # 規格審查 #11:裝置名稱長度
    device_name_max_length: int = 30
    default_device_name: str = "未命名鏡頭"

    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    # 規格審查 #4:配對是暴力破解的標的,單獨用更嚴的限流
    pair_rate_limit_requests: int = 10
    pair_rate_limit_window_seconds: int = 60
    # 規格審查 #2:register 匿名可呼叫,以 IP 限流避免灌入 pending 列
    register_rate_limit_requests: int = 5
    register_rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
