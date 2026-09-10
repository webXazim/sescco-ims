from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.permissions import membership_has_capability
from apps.accounts.roles import Capability
from apps.core.models import AuditArea, Company, CompanySettings
from apps.core.services.audit import record_audit_event


@transaction.atomic
def update_company_settings(
    *,
    actor_membership,
    timezone: str,
    currency_code: str,
    country_code: str,
    company_name: str | None = None,
    legal_name: str | None = None,
    request=None,
) -> CompanySettings:
    if not membership_has_capability(actor_membership, Capability.MANAGE_SETTINGS):
        raise PermissionDenied("Your role cannot manage company settings.")

    company = Company.objects.select_for_update().get(pk=actor_membership.company_id)
    settings = CompanySettings.objects.select_for_update().get(company=company)

    next_name = company.name if company_name is None else str(company_name).strip()
    next_legal_name = company.legal_name if legal_name is None else str(legal_name).strip()
    if not next_name:
        raise ValidationError({"company_name": "Company name is required."})
    if len(next_name) > Company._meta.get_field("name").max_length:
        raise ValidationError({"company_name": "Company name is too long."})
    if len(next_legal_name) > Company._meta.get_field("legal_name").max_length:
        raise ValidationError({"legal_name": "Legal name is too long."})

    if settings.currency_code != currency_code.strip().upper():
        # A company currency defines the monetary unit of payroll/settlement snapshots.
        # Once a calculated financial snapshot exists, changing it would reinterpret history.
        from apps.internal_payroll.models import PayrollRun
        from apps.rental_manpower.models import SupplierSettlement

        has_financial_history = (
            PayrollRun.objects.for_company(company).filter(calculated_at__isnull=False).exists()
            or SupplierSettlement.objects.for_company(company).filter(calculated_at__isnull=False).exists()
        )
        if has_financial_history:
            raise ValidationError({"currency_code": "Currency cannot be changed after financial calculations exist."})

    before = {
        "company_name": company.name,
        "legal_name": company.legal_name,
        "timezone": settings.timezone,
        "currency_code": settings.currency_code,
        "country_code": settings.country_code,
    }

    company.name = next_name
    company.legal_name = next_legal_name
    settings.timezone = timezone
    settings.currency_code = currency_code
    settings.country_code = country_code

    company.full_clean(exclude=("slug",))
    settings.full_clean()

    company_changed = before["company_name"] != company.name or before["legal_name"] != company.legal_name
    settings_changed = (
        before["timezone"] != settings.timezone
        or before["currency_code"] != settings.currency_code
        or before["country_code"] != settings.country_code
    )
    if company_changed:
        company.save(update_fields=("name", "legal_name", "updated_at"))
    if settings_changed:
        settings.save(update_fields=("timezone", "currency_code", "country_code", "updated_at"))

    # Keep the request membership/company object coherent after the locked copies are saved.
    actor_membership.company.name = company.name
    actor_membership.company.legal_name = company.legal_name
    try:
        cached_settings = actor_membership.company.settings
    except CompanySettings.DoesNotExist:
        cached_settings = None
    if cached_settings is not None:
        cached_settings.timezone = settings.timezone
        cached_settings.currency_code = settings.currency_code
        cached_settings.country_code = settings.country_code

    after = {
        "company_name": company.name,
        "legal_name": company.legal_name,
        "timezone": settings.timezone,
        "currency_code": settings.currency_code,
        "country_code": settings.country_code,
    }
    if before != after:
        record_audit_event(
            company=company,
            area=AuditArea.CORE,
            action="company.settings.updated",
            object_type="core.CompanySettings",
            object_id=settings.pk,
            object_label=company.name,
            actor_membership=actor_membership,
            before=before,
            after=after,
            request=request,
        )
    return settings
