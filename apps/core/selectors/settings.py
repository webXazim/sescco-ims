from __future__ import annotations

from apps.core.models import CompanySettings


def company_settings(company) -> CompanySettings:
    """Return the required one-to-one company settings record."""

    return company.settings
