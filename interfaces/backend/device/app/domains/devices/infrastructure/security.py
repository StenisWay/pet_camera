"""DeviceSecrets 與 PairingCodeFactory 的正式實作。"""

import secrets
from datetime import datetime, timedelta

from app.core.security import (
    generate_device_secret,
    hash_device_secret,
    verify_device_secret,
)
from app.domains.devices.application.ports import DeviceSecrets, PairingCodeFactory
from app.domains.devices.domain.pairing_code import CROCKFORD_ALPHABET, PairingCode


class Sha256DeviceSecrets(DeviceSecrets):
    def issue(self) -> tuple[str, str]:
        plaintext = generate_device_secret()
        return plaintext, hash_device_secret(plaintext)

    def verify(self, plaintext: str, secret_hash: str) -> bool:
        return verify_device_secret(plaintext, secret_hash)


class RandomPairingCodeFactory(PairingCodeFactory):
    """用 CSPRNG 從 Crockford 字母表抽碼。

    用 secrets 而不是 random:配對碼是「把別人的鏡頭綁到我帳號」的唯一憑證,
    random 的梅森旋轉法只要觀察到少量輸出就能還原內部狀態、預測後續的碼。
    """

    def __init__(self, *, length: int, ttl_seconds: int) -> None:
        self.length = length
        self.ttl_seconds = ttl_seconds

    def new_code(self, now: datetime) -> PairingCode:
        code = "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(self.length))
        return PairingCode(code=code, expires_at=now + timedelta(seconds=self.ttl_seconds))
