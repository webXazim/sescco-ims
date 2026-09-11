from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, Paginator
from django.db.models import QuerySet


@dataclass(frozen=True)
class ListControls:
    sort: str
    direction: str
    page: int | None
    page_size: int | None

    @property
    def ordering_prefix(self) -> str:
        return "-" if self.direction == "desc" else ""


def parse_list_controls(
    request,
    *,
    allowed_sorts: dict[str, str],
    default_sort: str,
    default_direction: str = "asc",
    max_page_size: int = 200,
) -> ListControls:
    sort = str(request.GET.get("sort") or default_sort).strip()
    if sort not in allowed_sorts:
        raise ValidationError({"sort": "Unknown sort field."})

    direction = str(request.GET.get("direction") or default_direction).strip().lower()
    if direction not in {"asc", "desc"}:
        raise ValidationError({"direction": "Sort direction must be asc or desc."})

    page_raw = str(request.GET.get("page") or "").strip()
    page_size_raw = str(request.GET.get("page_size") or "").strip()
    if not page_raw and not page_size_raw:
        return ListControls(sort=sort, direction=direction, page=None, page_size=None)

    try:
        page = int(page_raw or "1")
        page_size = int(page_size_raw or "50")
    except ValueError as exc:
        raise ValidationError({"page": "page and page_size must be positive integers."}) from exc
    if page < 1:
        raise ValidationError({"page": "page must be at least 1."})
    if page_size < 1 or page_size > max_page_size:
        raise ValidationError({"page_size": f"page_size must be between 1 and {max_page_size}."})
    return ListControls(sort=sort, direction=direction, page=page, page_size=page_size)


def apply_ordering(queryset: QuerySet, *, controls: ListControls, allowed_sorts: dict[str, str]) -> QuerySet:
    field = allowed_sorts[controls.sort]
    ordering = f"{controls.ordering_prefix}{field}"
    # Stable tie-breakers keep pagination deterministic. A UUID/integer pk is safe across
    # all Payroll master querysets and prevents rows jumping between adjacent pages.
    return queryset.order_by(ordering, "pk")


def serialize_list(
    queryset: QuerySet,
    *,
    controls: ListControls,
    serializer,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    if controls.page is None or controls.page_size is None:
        results = [serializer(item) for item in queryset]
        return results, {
            "count": len(results),
            "page": None,
            "pageSize": None,
            "totalPages": None,
            "sort": controls.sort,
            "direction": controls.direction,
        }

    paginator = Paginator(queryset, controls.page_size)
    try:
        page_obj = paginator.page(controls.page)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)
    return [serializer(item) for item in page_obj.object_list], {
        "count": paginator.count,
        "page": page_obj.number,
        "pageSize": controls.page_size,
        "totalPages": paginator.num_pages,
        "sort": controls.sort,
        "direction": controls.direction,
    }
