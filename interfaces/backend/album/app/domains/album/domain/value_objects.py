"""相簿查詢的值物件。建立當下就驗證,不合法的篩選條件根本組不出來。"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from app.domains.album.domain.exceptions import InvalidDateFilter, InvalidPageSize


def _parse_day(value: str, field: str) -> date:
    try:
        # 不用 date.fromisoformat:Python 3.11+ 會接受 "20260920" 這類緊湊格式,
        # 規格要求的是嚴格的 YYYY-MM-DD
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise InvalidDateFilter(f"{field} 的格式須為 YYYY-MM-DD") from exc


@dataclass(frozen=True)
class DateRange:
    """相簿的日期篩選(規格審查 #5)。

    App 端用單日 `date`,Web 端用區間 `from`/`to`(左側「最近 7 天 / 自訂範圍」篩選欄),
    兩者互斥。對外是日期,對內換算成 [start, end) 的時間區間,呼叫端不必再處理
    「含當日」的邊界。

    日期換算成時間區間時需要一個時區:相簿依日期分組用**台北時間**
    (12_spec 第 2.1 節),資料本身仍以 UTC 儲存(01_資料模型與儲存規格.md 第 2.0 節)。
    台北晚上 8 點拍的照片在 UTC 是隔天,分組時區選錯會讓使用者看到日期跑掉。

    tz 刻意不給預設值:忘了傳會直接是型別錯誤,而不是靜默用 UTC 算出錯誤的分組。
    """

    start: datetime | None = None
    end: datetime | None = None  # 開區間上界

    @classmethod
    def build(
        cls,
        *,
        tz: tzinfo,
        day: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> "DateRange":
        # 空字串視為「沒有指定」:Web 端清空篩選欄時送出的是 ?date=,不是 bug
        day, date_from, date_to = (v.strip() or None if v else None
                                   for v in (day, date_from, date_to))
        if day and (date_from or date_to):
            raise InvalidDateFilter("date 與 from/to 不可同時使用")
        if day:
            parsed = _parse_day(day, "date")
            return cls(
                start=datetime.combine(parsed, time.min, tzinfo=tz),
                end=datetime.combine(parsed + timedelta(days=1), time.min, tzinfo=tz),
            )
        start = (
            datetime.combine(_parse_day(date_from, "from"), time.min, tzinfo=tz)
            if date_from
            else None
        )
        # to 是「含當日」:上界取隔天 00:00,才不會漏掉當天 23:59 的項目
        end = (
            datetime.combine(_parse_day(date_to, "to") + timedelta(days=1), time.min, tzinfo=tz)
            if date_to
            else None
        )
        if start and end and start >= end:
            raise InvalidDateFilter("起始日期不可晚於結束日期")
        return cls(start=start, end=end)


@dataclass(frozen=True)
class PageSize:
    """相簿分頁筆數。未指定時用預設值,超過上限夾到上限,避免一次撈爆整個相簿。"""

    value: int

    @classmethod
    def build(cls, requested: int | None, *, default: int, maximum: int) -> "PageSize":
        # 不用 `requested or default`:0 是 falsy,會被靜默當成沒給而變成預設值
        if requested is None:
            return cls(default)
        if requested < 1:
            raise InvalidPageSize("limit 必須大於 0")
        return cls(min(requested, maximum))
