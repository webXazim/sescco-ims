from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError

from apps.rental_manpower.models import (
    RentalRateType,
    RentalTimesheetPeriodPolicy,
    RentalTimesheetProjectSettings,
)


DEFAULT_REGULAR_HOURS_PER_DAY = Decimal("10.00")
DEFAULT_OVERTIME_MULTIPLIER = Decimal("1.0000")
DEFAULT_OFF_WEEKDAYS = ("fri", "sat")
WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_RATE_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class RentalTimesheetPolicy:
    off_weekdays: tuple[str, ...]
    regular_hours_per_day: Decimal
    overtime_multiplier: Decimal
    automatic_overtime: bool
    source: str


def _validated_off_weekdays(values) -> tuple[str, ...]:
    raw = values if isinstance(values, (list, tuple)) else DEFAULT_OFF_WEEKDAYS
    result: list[str] = []
    allowed = set(WEEKDAY_KEYS)
    for value in raw:
        key = str(value or "").strip().lower()
        if key not in allowed:
            raise ValidationError({"off_weekdays": f"Unknown weekday: {value}."})
        if key not in result:
            result.append(key)
    return tuple(result)


def _policy_from_row(row, *, source: str) -> RentalTimesheetPolicy:
    return RentalTimesheetPolicy(
        off_weekdays=_validated_off_weekdays(getattr(row, "off_weekdays", DEFAULT_OFF_WEEKDAYS)),
        regular_hours_per_day=Decimal(getattr(row, "regular_hours_per_day", DEFAULT_REGULAR_HOURS_PER_DAY)),
        overtime_multiplier=Decimal(getattr(row, "overtime_multiplier", DEFAULT_OVERTIME_MULTIPLIER)),
        automatic_overtime=bool(getattr(row, "automatic_overtime", True)),
        source=source,
    )


def project_timesheet_policy(*, company, project) -> RentalTimesheetPolicy:
    row = RentalTimesheetProjectSettings.objects.for_company(company).filter(project=project).first()
    if row is None:
        return RentalTimesheetPolicy(
            off_weekdays=DEFAULT_OFF_WEEKDAYS,
            regular_hours_per_day=DEFAULT_REGULAR_HOURS_PER_DAY,
            overtime_multiplier=DEFAULT_OVERTIME_MULTIPLIER,
            automatic_overtime=True,
            source="default",
        )
    return _policy_from_row(row, source="project")


def effective_timesheet_policy(*, company, project, period=None) -> RentalTimesheetPolicy:
    if period is not None:
        row = RentalTimesheetPeriodPolicy.objects.for_company(company).filter(period=period).first()
        if row is not None:
            return _policy_from_row(row, source="period")
    return project_timesheet_policy(company=company, project=project)


def ensure_period_timesheet_policy(*, company, period) -> RentalTimesheetPeriodPolicy:
    row = RentalTimesheetPeriodPolicy.objects.for_company(company).filter(period=period).first()
    if row is not None:
        return row
    source = project_timesheet_policy(company=company, project=period.project)
    row = RentalTimesheetPeriodPolicy(
        company=company,
        period=period,
        off_weekdays=list(source.off_weekdays),
        regular_hours_per_day=source.regular_hours_per_day,
        overtime_multiplier=source.overtime_multiplier,
        automatic_overtime=source.automatic_overtime,
    )
    row.full_clean()
    row.save()
    return row


def split_daily_hours(hours: Decimal | int | float | str, policy: RentalTimesheetPolicy) -> tuple[Decimal, Decimal]:
    value = Decimal(str(hours or 0))
    if value <= 0 or not policy.automatic_overtime:
        return max(value, Decimal("0")), Decimal("0")
    limit = policy.regular_hours_per_day
    return min(value, limit), max(value - limit, Decimal("0"))


def scheduled_workdays_in_month(period_start: date, off_weekdays: tuple[str, ...] | list[str]) -> int:
    off = set(_validated_off_weekdays(off_weekdays))
    days = monthrange(period_start.year, period_start.month)[1]
    count = 0
    for day in range(1, days + 1):
        current = period_start.replace(day=day)
        if WEEKDAY_KEYS[current.weekday()] not in off:
            count += 1
    return max(1, count)


def overtime_base_hourly_rate_from_terms(*, rate_type, rate, policy: RentalTimesheetPolicy, period_start: date) -> Decimal:
    rate_value = Decimal(rate)
    regular = policy.regular_hours_per_day
    if regular <= 0:
        raise ValidationError({"regular_hours_per_day": "Regular working hours must be greater than zero."})
    if rate_type == RentalRateType.HOURLY:
        return rate_value.quantize(_RATE_QUANT, rounding=ROUND_HALF_UP)
    if rate_type == RentalRateType.DAILY:
        return (rate_value / regular).quantize(_RATE_QUANT, rounding=ROUND_HALF_UP)
    if rate_type == RentalRateType.MONTHLY:
        standard_hours = regular * Decimal(scheduled_workdays_in_month(period_start, policy.off_weekdays))
        if standard_hours <= 0:
            raise ValidationError({"regular_hours_per_day": "Monthly OT hourly rate cannot be derived from zero standard hours."})
        return (rate_value / standard_hours).quantize(_RATE_QUANT, rounding=ROUND_HALF_UP)
    raise ValidationError({"rate_type": f"Unsupported rental rate type: {rate_type}"})


def overtime_base_hourly_rate(*, assignment, policy: RentalTimesheetPolicy, period_start: date) -> Decimal:
    return overtime_base_hourly_rate_from_terms(
        rate_type=assignment.rate_type, rate=assignment.rate, policy=policy, period_start=period_start
    )


def overtime_bill_rate_from_terms(*, rate_type, rate, policy: RentalTimesheetPolicy, period_start: date) -> Decimal:
    return (
        overtime_base_hourly_rate_from_terms(rate_type=rate_type, rate=rate, policy=policy, period_start=period_start)
        * policy.overtime_multiplier
    ).quantize(_RATE_QUANT, rounding=ROUND_HALF_UP)


def overtime_bill_rate(*, assignment, policy: RentalTimesheetPolicy, period_start: date) -> Decimal:
    return overtime_bill_rate_from_terms(
        rate_type=assignment.rate_type, rate=assignment.rate, policy=policy, period_start=period_start
    )


def automatic_overtime_for_entries(entries, policy: RentalTimesheetPolicy) -> Decimal:
    total = Decimal("0")
    if not policy.automatic_overtime:
        return total
    for entry in entries:
        _regular, overtime = split_daily_hours(entry.regular_hours, policy)
        total += overtime
    return total


def date_is_policy_off_day(work_date: date, policy: RentalTimesheetPolicy) -> bool:
    return WEEKDAY_KEYS[work_date.weekday()] in set(policy.off_weekdays)
