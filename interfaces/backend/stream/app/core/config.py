"""Stream 訊令服務設定。

部署形狀見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md:服務複本跑在 VM-1/VM-2,
Redis 與 TURN server 是 VM-3 上的單例,透過 VCN 私有網路連線。

本服務不擁有任何 Postgres 資料表,所以沒有 database_url。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="STREAM_", extra="ignore")

    app_name: str = "Pet Camera Stream Service"
    debug: bool = False

    # 共用 Redis:session 暫存、signaling 喚醒、限流計數都放這裡(01_資料模型 第 7 節)
    redis_url: str = "redis://127.0.0.1:6379/0"

    # 與 Auth 服務共用的 JWT 簽章設定(Stream 只驗證,不簽發)
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"

    # 跨服務內部呼叫用的共享金鑰,只走 VCN 私有網路
    internal_api_key: str = "change-me-internal"

    # 06_spec 第 2.5 節:coturn REST API 認證(use-auth-secret)
    turn_urls: tuple[str, ...] = ("turn:127.0.0.1:3478?transport=udp",)
    turn_static_secret: str = ""
    # 憑證效期刻意長於 session TTL,不會出現 session 還在但憑證先過期的狀態
    turn_credential_ttl_seconds: int = 600

    # 06_spec 第 2.4 節
    session_ttl_seconds: int = 300
    # 第 3.1 節:offer 等待 answer 逾時 5 秒 -> STREAM_005
    answer_wait_timeout_seconds: float = 5.0
    # 第 3.2 節:鏡頭端長輪詢 30 秒無 offer 回 204
    pending_offer_poll_timeout_seconds: float = 30.0

    # 查詢鏡頭線上狀態的 Device 服務(跨服務邊界,不直接讀 devices 表)
    device_service_base_url: str = "http://127.0.0.1:8002"
    device_service_timeout_seconds: float = 2.0

    # 規格審查 #10:建立 session 是昂貴操作,每位使用者每分鐘 10 次
    session_rate_limit_requests: int = 10
    session_rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
