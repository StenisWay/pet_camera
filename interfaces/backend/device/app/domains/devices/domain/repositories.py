"""DeviceRepository:domain 對外層提出的存取合約。

先寫介面,再讓 infrastructure 與測試替身各自實作。每個抽象方法的 docstring 就是
**行為承諾**,合約測試(tests/domains/devices/contracts/)會逐條驗證,
確保 fake 與 SQLAlchemy 實作行為一致——application 層的測試全建立在 fake 上,
fake 若行為不同,測試會綠燈但上線出錯。

以聚合為單位(整個 Device 存取),不做泛用 CRUD:`update_status(id, status)` 這種方法
會讓呼叫端繞過實體的業務規則直接改狀態,規則就散掉了。
"""

import uuid
from abc import ABC, abstractmethod

from app.domains.devices.domain.entities import Device


class DeviceRepository(ABC):
    @abstractmethod
    async def get(self, device_id: uuid.UUID) -> Device | None:
        """依 id 取回裝置;不存在時回傳 None。

        回傳的是新的實體物件,對它的修改必須 save 才會被保存。
        """

    @abstractmethod
    async def get_by_hardware_id(self, hardware_id: str) -> Device | None:
        """依鏡頭硬體識別碼取回裝置;不存在時回傳 None。

        規格審查 #3:鏡頭重開機會再次呼叫 register,靠這個方法判斷是否已經註冊過,
        避免同一台實體鏡頭在 devices 表裡累積出多筆孤兒列。
        """

    @abstractmethod
    async def get_by_pairing_code(self, pairing_code: str) -> Device | None:
        """依配對碼取回裝置**並取得該列的獨佔權**;查無或該碼已被清除時回傳 None。

        傳入的是使用者原始輸入,實作必須先正規化(見 pairing_code.normalize)再查詢。
        已配對的裝置 pairing_code 為 null,因此一定查不到(審查 #5 的前提)。

        併發承諾(審查 #10):同一組配對碼的多個並行配對請求必須被**序列化**——
        第一個交易完成之前,第二個不能讀到同一列。少了這個承諾,兩個使用者同時輸入
        同一組碼會雙雙讀到 pending、雙雙寫入,後者覆蓋前者的 user_id,
        前一位使用者的 App 顯示配對成功、裝置卻不屬於他。
        """

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> list[Device]:
        """取回該使用者名下所有裝置,依 created_at 由舊到新排序。

        規格審查 #13:排序必須固定,否則使用者每次重整列表順序都不同。
        未配對(pending)的裝置沒有擁有者,不會出現在任何人的列表中。
        """

    @abstractmethod
    async def count_by_user(self, user_id: uuid.UUID) -> int:
        """該使用者已配對的裝置數量。規格審查 #13:用於檢查每帳號 20 台上限。"""

    @abstractmethod
    async def save(self, device: Device) -> None:
        """新增或更新整個聚合。實際寫入在 UnitOfWork.commit() 時才生效。"""
