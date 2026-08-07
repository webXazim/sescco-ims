from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.http import QueryDict
from django.utils import timezone


DATE_PRESETS = (
    ("", "Any date"),
    ("today", "Today"),
    ("yesterday", "Yesterday"),
    ("this_week", "This week"),
    ("last_7_days", "Last 7 days"),
    ("this_month", "This month"),
    ("last_30_days", "Last 30 days"),
    ("this_quarter", "This quarter"),
    ("this_year", "This year"),
    ("previous_year", "Previous year"),
    ("custom", "Custom range"),
)


@dataclass(frozen=True)
class DateRange:
    start: date | None
    end: date | None
    label: str


def resolve_date_range(
    preset: str,
    *,
    start: date | None = None,
    end: date | None = None,
    today: date | None = None,
) -> DateRange:
    today = today or timezone.localdate()
    if preset == "today":
        return DateRange(today, today, "Today")
    if preset == "yesterday":
        yesterday = today - timedelta(days=1)
        return DateRange(yesterday, yesterday, "Yesterday")
    if preset == "this_week":
        week_start = today - timedelta(days=today.weekday())
        return DateRange(week_start, today, "This week")
    if preset == "last_7_days":
        return DateRange(today - timedelta(days=6), today, "Last 7 days")
    if preset == "this_month":
        return DateRange(today.replace(day=1), today, "This month")
    if preset == "last_30_days":
        return DateRange(today - timedelta(days=29), today, "Last 30 days")
    if preset == "this_quarter":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        return DateRange(today.replace(month=quarter_month, day=1), today, "This quarter")
    if preset == "this_year":
        return DateRange(today.replace(month=1, day=1), today, "This year")
    if preset == "previous_year":
        year = today.year - 1
        return DateRange(date(year, 1, 1), date(year, 12, 31), "Previous year")
    if preset == "custom":
        if start and end:
            label = f"{start:%d %b %Y} – {end:%d %b %Y}"
        elif start:
            label = f"From {start:%d %b %Y}"
        elif end:
            label = f"Through {end:%d %b %Y}"
        else:
            label = "Custom range"
        return DateRange(start, end, label)
    return DateRange(None, None, "Any date")


def querydict_to_plain(query: QueryDict, allowed: Iterable[str]) -> dict[str, str | list[str]]:
    result: dict[str, str | list[str]] = {}
    for key in allowed:
        values = [value for value in query.getlist(key) if value not in (None, "")]
        if not values:
            continue
        result[key] = values if len(values) > 1 else values[0]
    return result


def plain_to_querydict(data: dict[str, str | list[str]]) -> QueryDict:
    query = QueryDict(mutable=True)
    for key, value in data.items():
        if isinstance(value, list):
            query.setlist(key, [str(item) for item in value])
        elif value not in (None, ""):
            query[key] = str(value)
    return query


def build_query_url(base_url: str, params: dict[str, str | list[str]]) -> str:
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        if isinstance(value, list):
            pairs.extend((key, str(item)) for item in value)
        elif value not in (None, ""):
            pairs.append((key, str(value)))
    encoded = urlencode(pairs)
    return f"{base_url}?{encoded}" if encoded else base_url


def decimal_label(value: Decimal | None) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    return format(normalized, "f")


def parse_decimal(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
