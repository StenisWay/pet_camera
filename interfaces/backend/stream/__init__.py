"""Stream 訊令服務——涵蓋 F1(即時串流)。

不擁有任何 Postgres 資料表。Session 狀態是短效的(直播期間才存在,結束即可捨棄),
存於共用 Redis 並附 TTL,不需要 Postgres 的持久性保證。此處仍定義 Repository 介面的
形狀,實作是 Redis-backed,只是不叫「資料表」。

Session 不能放服務本機記憶體:兩台 VM 各跑一份複本,Load Balancer 以請求為單位分流,
同一個 session 的「建立」「送出 offer」「結束」三個請求可能落在不同複本
(06_spec_即時串流.md 第 2.1 節)。

需要查詢裝置線上狀態(見 STREAM_001)時,呼叫 Device 服務的 API,
不直接讀取 Device 服務的資料——這是跨服務邊界,見
rule_doc/功能需求/13_ADR_微服務與三節點部署.md 第 4 節 CAP 判斷。

**本檔是對外契約**:給其他服務與規格書讀的。實作採 Clean Architecture,分為
domain / application / infrastructure / presentation 四層,單一領域:

    app/domains/streaming/    直播 session 與 WebRTC signaling

這裡的型別與介面對應實作的 **domain 層**(entities.py、value_objects.py、
repositories.py);tests/test_contract.py 驗證兩者不會走樣。實體是純 dataclass,
與 Redis 的序列化格式(infrastructure/redis_session_repository.py)分開。

規格審查後對原始介面的修改(決議見 06_spec_即時串流.md 第 9 節):
- Protocol 改為 ABC + @abstractmethod,實作明確繼承(漏實作時建立實例當下就失敗)。
- StreamSession 補上 owner_id 與 expires_at:沒有 owner_id 就無法驗證呼叫者
  (審查 #3 的 IDOR);沒有 expires_at 就沒有 TTL 語意(審查 #2)。
- StreamSession 納入 signaling 狀態(offer/answer/candidate):原介面只有 TURN 憑證,
  第 3.1/3.2 節的 SDP 與 ICE 交換沒有落腳處(審查 #1、#4)。
- TurnCredentials 補上 expires_at:第 2.5 節規定憑證效期必須長於 session TTL,
  沒有這個欄位就無法驗證。
- repository 的 create 改為 save:建立與更新走同一條路,接管語意(第 2.4 節)
  變成單一 key 的覆寫,不需要分散式鎖。
- 新增 get_active_for_device:接管與「目前誰在看」都需要由裝置反查 session,
  原介面只有 get_by_id,拿 device_id 查不到任何東西(審查 #1)。
- get_by_id 更名為 get,與其餘六個服務的 repository 一致。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

# 03_spec_裝置配對.md 第 2.3 節:心跳每 30 秒一次,超過 90 秒未回報即視為離線。
# 規格審查 #7:沒有人把 paired 轉成 offline,所以 Stream 自己看心跳新鮮度,
# 否則 STREAM_001 永遠不會觸發。
HEARTBEAT_TIMEOUT = timedelta(seconds=90)


@dataclass(frozen=True)
class TurnCredentials:
    """coturn REST API 認證憑證(06_spec 第 2.5 節)。

    credential 是 HMAC 簽章,不是密碼;簽發方式屬 infrastructure,本層只描述形狀。
    """

    urls: tuple[str, ...]
    username: str
    credential: str
    expires_at: datetime


@dataclass(frozen=True)
class IceCandidate:
    sdp_mid: str | None
    sdp_m_line_index: int | None
    candidate: str


class DeviceStatus(StrEnum):
    """值域與 devices.status 相同(01_資料模型與儲存規格.md 第 2.2 節),
    但這是 Stream 服務讀到的快照,不是它擁有的資料。"""

    PENDING = "pending"
    PAIRED = "paired"
    OFFLINE = "offline"


@dataclass(frozen=True)
class DeviceSnapshot:
    """向 Device 服務查到的鏡頭狀態快照。

    是否可串流由本服務判斷(見 is_online),Device 服務只提供原始資料。
    """

    device_id: uuid.UUID
    owner_id: uuid.UUID | None
    status: DeviceStatus
    last_seen_at: datetime | None

    def is_online(self, now: datetime) -> bool: ...

    def is_owned_by(self, user_id: uuid.UUID) -> bool: ...


class SignalingState(StrEnum):
    CREATED = "created"
    OFFERED = "offered"
    ANSWERED = "answered"


class Peer(StrEnum):
    """ICE candidate 的來源側。兩邊各自輪詢對方送出的 candidate。"""

    VIEWER = "viewer"
    CAMERA = "camera"


@dataclass
class StreamSession:
    """直播 session 聚合。TTL 300 秒(06_spec 第 2.4 節)。

    業務規則寫在方法裡,時間一律由外部傳入:
    - open:建立 session
    - is_expired / is_owned_by:存取控制
    - submit_offer:送出或重送 offer(重送會作廢舊的 answer,第 2.3 節的 ICE 重連)
    - accept_answer:鏡頭端回覆
    - add_candidate / candidates_for:ICE candidate 的雙向增量交換
    失效後呼叫任何 signaling 方法會拋 SessionExpired(STREAM_002)。
    """

    id: uuid.UUID
    device_id: uuid.UUID
    owner_id: uuid.UUID
    turn_credentials: TurnCredentials
    created_at: datetime
    expires_at: datetime
    state: SignalingState = SignalingState.CREATED
    offer_sdp: str | None = None
    answer_sdp: str | None = None
    viewer_candidates: list[IceCandidate] = field(default_factory=list)
    camera_candidates: list[IceCandidate] = field(default_factory=list)


class StreamSessionRepository(ABC):
    """Redis-backed。key 形狀見 06_spec 第 2.4 節:

        stream:session:{session_id} -> session,TTL = 剩餘效期
        stream:device:{device_id}   -> session_id,同 TTL
    """

    @abstractmethod
    async def get(self, session_id: uuid.UUID) -> StreamSession | None:
        """取回 session;不存在或已超過效期時回傳 None。

        回傳的是新的物件,對它的修改必須再 save 才會保存。
        """

    @abstractmethod
    async def get_active_for_device(self, device_id: uuid.UUID) -> StreamSession | None:
        """回傳該裝置目前的 session(供接管判斷);沒有則 None。

        同一支裝置至多一個 session——這是第 2.4 節接管語意的直接結果。
        """

    @abstractmethod
    async def save(self, session: StreamSession) -> None:
        """新增或覆寫 session,並把裝置索引指向它。

        接管語意(last-writer-wins):同一裝置既有的 session 會被這個取代,
        之後用舊 session_id 呼叫 get 必須回 None。
        效期以 session.expires_at 為準,到期後自動消失。
        """

    @abstractmethod
    async def delete(self, session_id: uuid.UUID) -> None:
        """刪除 session 與其裝置索引。

        不存在時視為成功(冪等)——第 3.1 節規定重複 DELETE 一律 204。
        """
