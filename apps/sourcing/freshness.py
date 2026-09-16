from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from .models import SourcingSettings


FRESHNESS_ALL = "all"
FRESHNESS_FRESH = "fresh"
FRESHNESS_NEEDS_VERIFICATION = "needs-verification"
FRESHNESS_STALE = "stale"
FRESHNESS_NEVER = "never"
FRESHNESS_VALUES = frozenset(
    {
        FRESHNESS_ALL,
        FRESHNESS_FRESH,
        FRESHNESS_NEEDS_VERIFICATION,
        FRESHNESS_STALE,
        FRESHNESS_NEVER,
    }
)


@dataclass(frozen=True, slots=True)
class SourcingFreshnessPolicy:
    fresh_for_days: int = 7
    stale_after_days: int = 30

    def cutoffs(self, *, now=None):
        moment = now or timezone.now()
        return (
            moment - timedelta(days=self.fresh_for_days),
            moment - timedelta(days=self.stale_after_days),
        )


def sourcing_freshness_policy(*, company) -> SourcingFreshnessPolicy:
    settings_row = (
        SourcingSettings.objects.for_company(company)
        .values("fresh_for_days", "stale_after_days")
        .first()
    )
    if not settings_row:
        return SourcingFreshnessPolicy()
    fresh_for_days = max(1, int(settings_row.get("fresh_for_days") or 7))
    stale_after_days = max(fresh_for_days + 1, int(settings_row.get("stale_after_days") or 30))
    return SourcingFreshnessPolicy(
        fresh_for_days=fresh_for_days,
        stale_after_days=stale_after_days,
    )


def freshness_key(value, *, policy: SourcingFreshnessPolicy, now=None) -> str:
    if value is None:
        return FRESHNESS_NEVER
    fresh_cutoff, stale_cutoff = policy.cutoffs(now=now)
    if value >= fresh_cutoff:
        return FRESHNESS_FRESH
    if value >= stale_cutoff:
        return FRESHNESS_NEEDS_VERIFICATION
    return FRESHNESS_STALE


def freshness_label(key: str) -> str:
    return {
        FRESHNESS_FRESH: "Fresh",
        FRESHNESS_NEEDS_VERIFICATION: "Needs verification",
        FRESHNESS_STALE: "Stale",
        FRESHNESS_NEVER: "Never verified",
    }.get(key, "Unknown")


def freshness_age_days(value, *, now=None) -> int | None:
    if value is None:
        return None
    moment = now or timezone.now()
    delta = moment - value
    return max(0, delta.days)
