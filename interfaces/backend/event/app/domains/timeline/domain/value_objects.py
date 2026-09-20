"""時間軸查詢的輸入值物件:游標、分頁上限、日期區間。

08_spec_時間軸與事件歷史.md 第 2.1 節。這些型別的存在理由是把「使用者送來什麼都有
可能」收斂成「內部只會拿到合法的形狀」——application 與 infrastructure 因此不必再
逐一檢查 limit 有沒有超過上限、date 是不是真的日期。
"""

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.shared_kernel.errors import BusinessRuleViolation

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_TIMEZONE = "Asia/Taipei"


class InvalidCursor(BusinessRuleViolation):
    """游標格式不正確"""


class InvalidPageSize(BusinessRuleViolation):
    """每頁筆數超出允許範圍"""


class InvalidDateFilter(BusinessRuleViolation):
    """日期篩選條件不正確"""


@dataclass(frozen=True)
class TimelineCursor:
    """(started_at, id) 組合游標。

    同一秒可能有多筆事件,只靠 started_at 分頁會在捲動時重複或遺漏,所以帶上 id 決勝。
    時間以微秒整數編碼:秒級精度不夠,而浮點數會在往返時掉精度。

    對外是一段不透明的 base64——前端一旦看得懂游標內容就會開始自己組,之後排序規則
    就再也改不動了。
    """

    started_at: datetime
    event_id: UUID

    def encode(self) -> str:
        micros = int(self.started_at.timestamp() * 1_000_000)
        raw = f"{micros}|{self.event_id}"
        return base64.urlsafe_b64encode(raw.encode()).decode()

    @classmethod
    def decode(cls, value: str) -> "TimelineCursor":
        """解不開時丟 InvalidCursor(VAL_001);竄改的游標不該變成 500。"""
        try:
            raw = base64.urlsafe_b64decode(value.encode()).decode()
            micros, event_id = raw.split("|", 1)
            return cls(
                started_at=datetime.fromtimestamp(int(micros) / 1_000_000, tz=UTC),
                event_id=UUID(event_id),
            )
        except (ValueError, binascii.Error, UnicodeDecodeError, OverflowError, OSError) as exc:
            raise InvalidCursor() from exc


@dataclass(frozen=True)
class PageSize:
    value: int

    @classmethod
    def of(cls, limit: int | None) -> "PageSize":
        """未指定用預設 20;上限 100——沒有上限的 limit 會讓單一請求拖垮 VM-3。"""
        if limit is None:
            return cls(DEFAULT_PAGE_SIZE)
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise InvalidPageSize()
        return cls(limit)


@dataclass(frozen=True)
class DateRange:
    """已換算成 UTC 的查詢區間([started_from, started_to),上界不含)。

    單日(date + tz)與區間(from/to)兩種輸入都先收斂成這一種形狀,
    repository 因此只需要處理一種情況。
    """

    started_from: datetime | None
    started_to: datetime | None

    @classmethod
    def resolve(
        cls,
        *,
        date: str | None = None,
        tz: str | None = None,
        started_from: int | None = None,
        started_to: int | None = None,
    ) -> "DateRange":
        """date 與 from/to 互斥(第 2.1 節)。from/to 是 Unix timestamp(秒)。"""
        if date is not None and (started_from is not None or started_to is not None):
            raise InvalidDateFilter()
        if date is not None:
            return cls._single_day(date, tz or DEFAULT_TIMEZONE)
        return cls._from_timestamps(started_from, started_to)

    @classmethod
    def _single_day(cls, date: str, tz: str) -> "DateRange":
        """使用者說的「某一天」是他所在時區的一天,資料卻以 UTC 儲存。

        不換算的話,台北時間傍晚之後的事件會被歸到隔天(規格審查 #6)。
        """
        try:
            # 用 strptime 而不是 fromisoformat:後者在 3.11+ 也接受 "20260920"
            # 這種基本格式,規格寫的是 YYYY-MM-DD,寬鬆解析會讓兩種格式都流進來
            day = datetime.strptime(date, "%Y-%m-%d").date()
            zone = ZoneInfo(tz)
        except (ValueError, ZoneInfoNotFoundError, ModuleNotFoundError) as exc:
            raise InvalidDateFilter() from exc

        start_local = datetime.combine(day, time.min, tzinfo=zone)
        return cls(
            started_from=start_local.astimezone(UTC),
            started_to=(start_local + timedelta(days=1)).astimezone(UTC),
        )

    @classmethod
    def _from_timestamps(cls, started_from: int | None, started_to: int | None) -> "DateRange":
        try:
            lower = datetime.fromtimestamp(started_from, tz=UTC) if started_from else None
            upper = datetime.fromtimestamp(started_to, tz=UTC) if started_to else None
        except (ValueError, OverflowError, OSError, TypeError) as exc:
            raise InvalidDateFilter() from exc

        if lower and upper and upper < lower:
            # 顛倒的區間只會回空列表,對使用者是無聲的錯誤,不如直接擋下
            raise InvalidDateFilter()
        return cls(started_from=lower, started_to=upper)
