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
    commercial_registration: str | None = None,
    vat_number: str | None = None,
    document_address: str | None = None,
    document_email: str | None = None,
    document_phone: str | None = None,
    website: str | None = None,
    document_branding_mode: str | None = None,
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
        "commercial_registration": settings.commercial_registration,
        "vat_number": settings.vat_number,
        "document_address": settings.document_address,
        "document_email": settings.document_email,
        "document_phone": settings.document_phone,
        "website": settings.website,
        "document_branding_mode": settings.document_branding_mode,
    }

    company.name = next_name
    company.legal_name = next_legal_name
    settings.timezone = timezone
    settings.currency_code = currency_code
    settings.country_code = country_code
    if commercial_registration is not None:
        settings.commercial_registration = commercial_registration
    if vat_number is not None:
        settings.vat_number = vat_number
    if document_address is not None:
        settings.document_address = document_address
    if document_email is not None:
        settings.document_email = document_email
    if document_phone is not None:
        settings.document_phone = document_phone
    if website is not None:
        settings.website = website
    if document_branding_mode is not None:
        settings.document_branding_mode = document_branding_mode

    company.full_clean(exclude=("slug",))
    settings.full_clean()

    company_changed = before["company_name"] != company.name or before["legal_name"] != company.legal_name
    settings_changed = (
        before["timezone"] != settings.timezone
        or before["currency_code"] != settings.currency_code
        or before["country_code"] != settings.country_code
        or before["commercial_registration"] != settings.commercial_registration
        or before["vat_number"] != settings.vat_number
        or before["document_address"] != settings.document_address
        or before["document_email"] != settings.document_email
        or before["document_phone"] != settings.document_phone
        or before["website"] != settings.website
        or before["document_branding_mode"] != settings.document_branding_mode
    )
    if company_changed:
        company.save(update_fields=("name", "legal_name", "updated_at"))
    if settings_changed:
        settings.save(update_fields=(
            "timezone", "currency_code", "country_code", "commercial_registration", "vat_number",
            "document_address", "document_email", "document_phone", "website", "document_branding_mode", "updated_at",
        ))

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
        cached_settings.commercial_registration = settings.commercial_registration
        cached_settings.vat_number = settings.vat_number
        cached_settings.document_address = settings.document_address
        cached_settings.document_email = settings.document_email
        cached_settings.document_phone = settings.document_phone
        cached_settings.website = settings.website
        cached_settings.document_branding_mode = settings.document_branding_mode

    after = {
        "company_name": company.name,
        "legal_name": company.legal_name,
        "timezone": settings.timezone,
        "currency_code": settings.currency_code,
        "country_code": settings.country_code,
        "commercial_registration": settings.commercial_registration,
        "vat_number": settings.vat_number,
        "document_address": settings.document_address,
        "document_email": settings.document_email,
        "document_phone": settings.document_phone,
        "website": settings.website,
        "document_branding_mode": settings.document_branding_mode,
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


_BRAND_ASSET_FIELDS = {
    "logo": "document_logo",
    "letterhead": "document_letterhead",
    "watermark": "document_watermark",
}


@transaction.atomic
def update_company_brand_asset(*, actor_membership, kind: str, uploaded_file=None, clear: bool = False, request=None) -> CompanySettings:
    """Version the active company document-brand asset without deleting historical files.

    Finalized documents snapshot the storage key + SHA-256 of the active asset.  Replacing or
    clearing the current setting therefore must not delete the previous file because historical
    immutable documents may still reference it.
    """
    if not membership_has_capability(actor_membership, Capability.MANAGE_SETTINGS):
        raise PermissionDenied("Your role cannot manage company settings.")
    field_name = _BRAND_ASSET_FIELDS.get(str(kind).strip().lower())
    if field_name is None:
        raise ValidationError({"kind": "Unsupported branding asset."})
    if clear == (uploaded_file is not None):
        raise ValidationError({"asset": "Provide one branding file or request a clear operation."})

    company = Company.objects.select_for_update().get(pk=actor_membership.company_id)
    settings = CompanySettings.objects.select_for_update().get(company=company)
    field = getattr(settings, field_name)
    before_name = field.name or ""
    if clear:
        setattr(settings, field_name, "")
    else:
        field.save(uploaded_file.name, uploaded_file, save=False)
    settings.full_clean()
    settings.save(update_fields=(field_name, "updated_at"))

    record_audit_event(
        company=company,
        area=AuditArea.CORE,
        action="company.document_branding.updated",
        object_type="core.CompanySettings",
        object_id=settings.pk,
        object_label=f"{company.name} · {kind}",
        actor_membership=actor_membership,
        before={"kind": kind, "configured": bool(before_name)},
        after={"kind": kind, "configured": bool(getattr(settings, field_name).name)},
        request=request,
    )
    return settings
