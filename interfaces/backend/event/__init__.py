"""Event 服務——涵蓋 F2(事件偵測,背景 worker,不對外提供 API)+ F3(時間軸讀取 API)。
擁有 events 表。兩者合併成一個服務的理由見
rule_doc/功能需求/13_ADR_微服務與三節點部署.md 第 1 節(同一張表不可被兩個服務分別宣稱擁有)。

**本檔是對外契約**:給其他服務與規格書讀的。實作採 Clean Architecture,分為兩個領域,
每個領域再分 domain / application / infrastructure / presentation 四層:

    app/domains/detection/    F2:錄影會話與事件寫入(07_spec)
    app/domains/timeline/     F3:時間軸讀取、播放換發、已讀標記(08_spec)

兩個領域對應同一張 events 表,但邊界不同:detection 推進事件的生命週期
(processing → ready / failed),timeline 只讀,外加 is_read 這個純閱讀狀態。
這是 ADR 第 1 節「F2 寫、F3 讀」在程式結構上的對應;共用的資料列定義放
app/core/orm.py,兩個領域各自用自己的 mapper 轉成自己的型別。

這裡的型別與介面對應實作的 **domain 層**(entities.py、repositories.py);
tests/test_contract.py 驗證兩者不會走樣。實體是純 dataclass,與 SQLAlchemy 的資料列
分開,由 mapper 轉換——資料表可以依 01_資料模型與儲存規格.md 自由演進而不牽動業務規則。

規格審查後對原始介面的修改(理由見 README 的「規格審查結論」):
- 介面一律改用 ABC + @abstractmethod,實作明確繼承(漏實作時建立實例當下就失敗)。
- confidence_score 改用 Decimal:資料表是 numeric(3,2),用 float 比較 0.6 門檻會有誤差。
- 新增 is_partial:斷線產生的不完整片段(EVENT_003)在原本的三態狀態機沒有落腳處,
  而 failed 的語意是「沒有可播放內容」,不能拿來表達「可播放但不完整」。
- 新增 DeviceOwnership port:events 沒有 user_id,原介面無法驗證擁有者,等於任何
  登入者都能讀取與播放他人的寵物影片(IDOR)。非本人一律回 404,不洩漏存在性。
- delete_all_by_device 改為回傳被刪事件的 R2 object key,並由本服務自己清除物件——
  原註解要求呼叫端(Device 服務)刪 R2,但它不知道 event_id,組不出 key。
- create_processing / mark_ready / mark_failed 這類「直接改欄位」的方法收進 Event 實體,
  repository 只負責 get / save 聚合,不提供繞過業務規則的欄位級更新。
- 列表查詢移出 repository,改由 application 的 TimelineQueries 讀取端負責
  (純查詢、沒有業務規則,直接回傳 DTO)。
- 新增 PushNotifier port:07_spec 第 3 節的「ready 後觸發推播」原本沒有對應的呼叫路徑。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

# ---- 07_spec 第 2 節的錄影規則 ----
MOTION_THRESHOLD = Decimal("0.60")  # 超過此分數觸發事件(第 2.1 節)
SILENCE_TIMEOUT = timedelta(seconds=5)  # 活動停止超過 5 秒結束錄影(第 2.2 節)
MAX_RECORDING_DURATION = timedelta(seconds=60)  # 單一事件錄影上限(第 2.2 節)
UPLOAD_MAX_ATTEMPTS = 3  # 上傳 R2 重試 3 次後收斂為 failed(第 3 節)

# ---- 01_資料模型 第 3.2 節的 R2 lifecycle,08_spec 第 2.2 節以此判定過期 ----
VIDEO_RETENTION = timedelta(days=7)
THUMBNAIL_RETENTION = timedelta(days=30)

# ---- 08_spec 第 2.1 節的分頁 ----
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_TIMEZONE = "Asia/Taipei"  # date 篩選未指定 tz 時的預設


class EventType(StrEnum):
    MOTION = "motion"


class EventStatus(StrEnum):
    """01_資料模型與儲存規格.md 第 4 節的事件處理狀態機。"""

    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class UploadedMedia:
    """上傳完成後的產物,由 detection 的 use case 交給 Event.mark_ready。"""

    video_object_key: str
    thumbnail_object_key: str
    confidence_score: Decimal
    duration_sec: int
    ended_at: datetime
    is_partial: bool = False


# =====================================================================
# detection(F2):事件寫入側
# =====================================================================


@dataclass
class Event:
    """events 表的聚合。狀態轉移只能透過方法,外部不直接改 status。"""

    id: uuid.UUID
    device_id: uuid.UUID
    started_at: datetime
    event_type: EventType = EventType.MOTION
    status: EventStatus = EventStatus.PROCESSING
    confidence_score: Decimal = Decimal("0.00")
    video_object_key: str | None = None
    thumbnail_object_key: str | None = None
    duration_sec: int | None = None
    ended_at: datetime | None = None
    is_read: bool = False
    # 斷線導致的不完整片段(EVENT_003);ready 才有意義
    is_partial: bool = False

    @classmethod
    def begin(cls, *, id: uuid.UUID, device_id: uuid.UUID, started_at: datetime) -> "Event":
        """偵測 worker 觸發錄影當下建立,status=processing(07_spec 第 3.1 節)。"""

    def mark_ready(self, media: UploadedMedia) -> None:
        """上傳成功,轉 ready(第 3.4 節)。

        confidence_score 取事件期間最高值,duration_sec 為實際長度。
        已經是終態(ready / failed)時丟 EventAlreadyFinalised——重試不該改寫結果。
        """

    def mark_failed(self) -> None:
        """重試 3 次後仍上傳失敗,轉 failed(第 3.5 節)。不建立可播放內容。"""

    @property
    def is_finalised(self) -> bool:
        """是否已離開 processing。"""

    def object_keys(self) -> list[str]:
        """刪除事件時要一併清掉的 R2 物件(影片 + 縮圖),未上傳的不列入。"""


@dataclass
class RecordingSession:
    """一次錄影的進行狀態。07_spec 第 2.1、2.2 節的合併與結束規則都在這裡。

    純值物件,不碰 I/O:影格從哪來、怎麼編碼都是 worker 的 adapter 的事,
    這裡只回答「這個影格要不要延續錄影」「現在該不該結束」。
    """

    event_id: uuid.UUID
    device_id: uuid.UUID
    started_at: datetime
    last_motion_at: datetime
    peak_score: Decimal

    @classmethod
    def start(
        cls, *, event_id: uuid.UUID, device_id: uuid.UUID, at: datetime, score: Decimal
    ) -> "RecordingSession":
        """分數超過門檻時開始錄影。低於門檻不該走到這裡。"""

    def observe(self, *, at: datetime, score: Decimal) -> None:
        """吃進一個影格的分數。

        超過門檻視為活動延續,更新 last_motion_at 與 peak_score——這就是第 2.1 節
        「錄影期間的後續活動視為同一事件延續,不建立新事件」。
        """

    def should_stop(self, now: datetime) -> bool:
        """活動停止超過 SILENCE_TIMEOUT,或已達 MAX_RECORDING_DURATION 上限。"""

    def stop_reason(self, now: datetime) -> "StopReason | None":
        """結束原因;還不該結束時回 None。"""

    def duration_sec(self, ended_at: datetime) -> int:
        """實際錄影長度,至少 1 秒(資料表 CHECK 要求 > 0)。"""


class StopReason(StrEnum):
    SILENCE = "silence"  # 活動停止超過 5 秒
    MAX_DURATION = "max_duration"  # 達 60 秒上限,強制結束
    DISCONNECTED = "disconnected"  # 鏡頭斷線,片段不完整(is_partial=true)


class EventRepository(ABC):
    """以聚合為單位的存取。列表查詢不在這裡,見 TimelineQueries。"""

    @abstractmethod
    async def get(self, event_id: uuid.UUID) -> Event | None:
        """取回單一事件;不存在時回傳 None。修改後必須 save 才會保存。"""

    @abstractmethod
    async def save(self, event: Event) -> None:
        """新增或更新整個聚合。實際寫入在 UnitOfWork.commit() 時生效。"""

    @abstractmethod
    async def delete_all_by_device(self, device_id: uuid.UUID) -> list[str]:
        """刪除該裝置所有事件,回傳被刪事件對應的 R2 object key(影片 + 縮圖)。

        由 Device 服務在移除裝置時透過 DELETE /internal/devices/{device_id}/events
        觸發(01_資料模型與儲存規格.md 第 6 節)。R2 物件由本服務清除,不是呼叫端——
        key 需要 event_id 與事件日期,Device 服務組不出來。
        """


class ObjectStorage(ABC):
    """R2。detection 用來上傳,timeline 用來換發 presigned URL、刪除物件。"""

    @abstractmethod
    async def upload(self, key: str, data: bytes, *, content_type: str) -> None:
        """上傳物件。失敗時丟 StorageUnavailable,由 use case 決定重試。"""

    @abstractmethod
    async def presigned_url(self, key: str, *, expires_in: timedelta) -> str:
        """換發短效下載連結(08_spec 第 2.2 節:10 分鐘)。

        注意:presigned URL 無法做到真正的一次性,有效期內可重複使用。
        """

    @abstractmethod
    async def delete_many(self, keys: list[str]) -> None:
        """刪除多個物件;不存在的 key 不視為錯誤(冪等)。"""


class PushNotifier(ABC):
    """Push 服務(09_spec 第 3.1 節)。ready 之後才呼叫。"""

    @abstractmethod
    async def notify_event_ready(
        self,
        *,
        device_id: uuid.UUID,
        event_id: uuid.UUID,
        confidence_score: Decimal,
        thumbnail_object_key: str | None,
        started_at: datetime,
    ) -> None:
        """觸發推播。裝置名稱與防洗版計數窗由 Push 服務負責,這裡不傳也不判斷。

        參數對應 POST /internal/notifications/event-ready 的 body
        (09_spec 第 3 節、push/__init__.py 的 EventReadyNotification)。
        縮圖 key 與 started_at 由本服務夾帶,不讓 Push 反過來查 events——
        Push 沒有 events 表,只靠 event_id 也組不出 R2 key(key 含事件日期)。

        失敗不應該回頭改動事件狀態:事件已經 ready 是事實,推播沒送出是另一回事。
        """


# =====================================================================
# timeline(F3):讀取側
# =====================================================================


@dataclass
class TimelineEvent:
    """時間軸用的唯讀視圖。播放與過期規則都在這裡(08_spec 第 2.2 節)。"""

    id: uuid.UUID
    device_id: uuid.UUID
    status: EventStatus
    confidence_score: Decimal
    started_at: datetime
    duration_sec: int | None
    is_read: bool
    is_partial: bool
    ended_at: datetime | None = None
    video_object_key: str | None = None
    thumbnail_object_key: str | None = None

    def ensure_playable(self, now: datetime) -> None:
        """可否換發播放連結。不可播時丟對應的領域例外:

        processing → EventNotReady(TIMELINE_005 / 409)
        failed     → EventProcessingFailed(EVENT_001 / 409)
        影片已過保留期(started_at + 7 天)→ VideoExpired(TIMELINE_002 / 410)
        """

    def thumbnail_available(self, now: datetime) -> bool:
        """縮圖是否還在保留期內(started_at + 30 天)且已產生。

        否則列表的 thumbnail_url 為 null,前端顯示佔位圖示(TIMELINE_004)。
        """

    def mark_read(self, is_read: bool) -> None:
        """標記已讀/未讀(08_spec 第 2.3 節)。只有這一個欄位可由用戶端改。"""


@dataclass(frozen=True)
class TimelineCursor:
    """(started_at, id) 組合游標。同一秒可能有多筆事件,只靠時間會重複或遺漏。"""

    started_at: datetime
    event_id: uuid.UUID

    def encode(self) -> str:
        """base64 字串,對外不透露內部欄位。"""

    @classmethod
    def decode(cls, value: str) -> "TimelineCursor":
        """解不開時丟 InvalidCursor(VAL_001),不要讓竄改的游標變成 500。"""


@dataclass(frozen=True)
class TimelineQuery:
    """列表查詢條件(08_spec 第 2.1 節)。date 與 from/to 互斥,由此型別保證。"""

    device_id: uuid.UUID
    cursor: TimelineCursor | None = None
    limit: int = DEFAULT_PAGE_SIZE
    # 解析後的 UTC 區間:單日(date + tz)與區間(from/to)都先換算成這個形狀,
    # 讓 repository 只需要處理一種情況。
    started_from: datetime | None = None
    started_to: datetime | None = None


@dataclass
class TimelinePage:
    items: list[TimelineEvent]
    next_cursor: TimelineCursor | None


class TimelineQueries(ABC):
    """讀取端。純查詢、沒有業務規則,不經過聚合(CQRS 的讀取側)。"""

    @abstractmethod
    async def list_by_device(self, query: TimelineQuery) -> TimelinePage:
        """依 started_at 由新到舊分頁,回傳全部三種 status。

        沒有下一頁時 next_cursor 為 None。資料層不可用時丟 ServiceUnavailable,
        **不可回空列表**(ADR 第 4 節:Event 讀取選 C)。
        """

    @abstractmethod
    async def get(self, event_id: uuid.UUID) -> TimelineEvent | None:
        """取回單一事件的唯讀視圖;不存在時回傳 None。"""


class DeviceOwnership(ABC):
    """Device 服務(04_spec 第 3 節的 GET /internal/devices/{device_id})。

    events 沒有 user_id,devices 表也不屬於本服務,但三個對外端點都必須驗證擁有者,
    否則任何登入者都能看別人的寵物影片(規格審查 #2)。
    """

    @abstractmethod
    async def is_owned_by(self, device_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """該裝置目前是否屬於這個使用者。

        裝置不存在、未配對、或屬於別人一律回 False,呼叫端一律回 404 DEVICE_005
        ——回 403 等於承認這個 id 存在。
        """
