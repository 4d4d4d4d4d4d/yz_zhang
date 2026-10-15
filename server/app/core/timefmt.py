"""TZ-060/062 时间进出 API 的唯一口径（58 号 spec）。

平台内部全部用**朴素 UTC**（`utcnow()` 返回 `datetime.now(timezone.utc)`
去掉 tzinfo 的值）。这个选择本身没问题，出问题的是它**没有说出来**：
响应里一律 `iso(x)`，给出去的是 `2026-09-20T08:00:00`——没有 `Z`。

而 JavaScript 的规矩是：ISO 8601 的日期时间形式不带偏移时按**本地时间**解析。
于是全站每一个时间显示都偏了用户所在时区的偏移量。代码里已经有两处
`new Date(iso + 'Z')` 的手工补丁——**补丁本身就是缺陷报告**，同样的问题
在别处还有七处没补。

所以这里只有两个函数，一个管出、一个管进，别处不许再自己拼。
"""
from datetime import date, datetime, timezone
from typing import Annotated, Any

from pydantic import AfterValidator


def iso(dt: datetime | None) -> str | None:
    """出口：朴素值视为 UTC，带时区的先换算到 UTC，一律以 `Z` 结尾。

    `None` 原样返回 `None`——调用点大多是可空字段，让它们少写一个三元表达式，
    顺便消灭 `iso(x)` 这个抄了七十多遍的句式。
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat() + "Z"


def to_utc_naive(value: Any) -> Any:
    """入口：把带偏移的时间**换算**到 UTC，而不是把偏移丢掉。

    改造前 `"2030-01-01T10:00:00+08:00"` 直接存成了 `10:00`——整整差 8 小时，
    且没有任何报错。正确的是 `02:00`。

    朴素值视为 UTC。另一种做法是**拒收**朴素值、逼客户端必须带偏移，更严格；
    但那会把所有既有集成方（包括开放 API 的第三方）一次性打断，而他们发的
    朴素值多半本来就是 UTC——**换算比拒收温和，且不会把已经对的用法判成错**。
    """
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


# 用在所有**用户提交**的时间字段上。内部生成的时间不需要它（本来就是 utcnow）。
# 用 AfterValidator 而不是 Before：要拿到 pydantic 解析好的 datetime，
# 在字符串阶段自己解析偏移等于把 pydantic 那套又写一遍。
UtcDatetime = Annotated[datetime, AfterValidator(to_utc_naive)]


def day(d: date | None) -> str | None:
    """日期（不是时间点）的出口：`YYYY-MM-DD`，没有时区可言——申报截止、记账日期、政策有效期。

    传进来的若是 datetime 直接拒绝：时间点必须走 `iso()`，不能悄悄截成日期。
    """
    if d is None:
        return None
    if isinstance(d, datetime):
        raise TypeError("时间点请用 iso()，day() 只收日期")
    return d.isoformat()


# TZ-068 导出文件里的时间（143 号 spec）：CSV / 表格没有「本地化显示」这一层，
# 一列裸的 `2026-10-14T00:30:00Z` 被人在表格里一看就是「10 月 14 日零点半」，实际是北京时间早上八点半。
# 所以导出一律换成北京时间，并且**在表头写明时区**——不写明的时间列等于没给时间。
EXPORT_TZ_LABEL = "北京时间 UTC+8"


def export_time(dt: datetime | None) -> str:
    """导出用：北京时间 `YYYY-MM-DD HH:MM:SS`（朴素值视为 UTC）。表头用 `EXPORT_TZ_LABEL` 写明时区。"""
    if dt is None:
        return ""
    from zoneinfo import ZoneInfo

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
