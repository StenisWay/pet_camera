"""刪除帳號時的跨服務清除(05_spec 第 2.2 節、01_資料模型 第 6 節)。

Auth 不直接寫 devices / media_items——那是別的服務擁有的表(13_ADR 第 1 節),
一律透過對方的內部端點。內部端點只走 VCN 私有網路、不經 Load Balancer,
另以共享金鑰標頭 `X-Internal-Api-Key` 把關。

**冪等**是規格對這兩個端點的要求:Auth 重試時資料已清空,對方必須回成功。
這裡把 404 也當成功,正是為了讓「已經沒有東西可刪」不要變成永遠重試不完的錯誤。
"""

import uuid

import httpx

from app.domains.accounts.application.ports import AccountPurger

INTERNAL_KEY_HEADER = "X-Internal-Api-Key"


class HttpAccountPurger(AccountPurger):
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        name: str,
        base_url: str,
        path_template: str,
        api_key: str,
    ) -> None:
        self.name = name
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._path_template = path_template
        self._api_key = api_key

    async def purge(self, user_id: uuid.UUID) -> None:
        url = self._base_url + self._path_template.format(user_id=user_id)
        response = await self._client.delete(
            url, headers={INTERNAL_KEY_HEADER: self._api_key}
        )
        if response.status_code == httpx.codes.NOT_FOUND:
            # 已經沒有東西可刪:重試路徑上的正常情況,不是失敗
            return
        response.raise_for_status()


def device_purger(
    client: httpx.AsyncClient, *, base_url: str, api_key: str
) -> HttpAccountPurger:
    """04_spec_裝置管理.md 第 3 節。"""
    return HttpAccountPurger(
        client,
        name="device",
        base_url=base_url,
        path_template="/internal/users/{user_id}/devices",
        api_key=api_key,
    )


def album_purger(
    client: httpx.AsyncClient, *, base_url: str, api_key: str
) -> HttpAccountPurger:
    """12_spec_相簿與雲端匯出.md 第 3 節。"""
    return HttpAccountPurger(
        client,
        name="album",
        base_url=base_url,
        path_template="/internal/users/{user_id}/media",
        api_key=api_key,
    )
