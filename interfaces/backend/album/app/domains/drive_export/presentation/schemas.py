"""Google Drive 授權與匯出 API 的 Pydantic 模型。只在 presentation 層使用。"""

import uuid

from pydantic import BaseModel, Field


class ExportRequestIn(BaseModel):
    # 規格審查 #6:單次上限 50 筆,在 schema 就擋掉,不必進到 use case
    media_item_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class ExportAcceptedOut(BaseModel):
    accepted_ids: list[uuid.UUID]
    skipped_ids: list[uuid.UUID]  # 已在匯出中,未重複送出


class OAuthUrlOut(BaseModel):
    authorization_url: str


class OAuthCallbackIn(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=512)
