from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .access import (
    membership_can_manage_sourcing_masters,
    membership_can_manage_manpower_sourcing,
    membership_can_manage_vendor_sourcing,
    membership_can_export_sourcing,
    membership_can_view_sourcing_masters,
    membership_can_view_manpower_sourcing,
    membership_can_view_vendor_sourcing,
    membership_has_any_sourcing_access,
    sourcing_access_context,
)
from .forms import (
    SourcingMaterialForm,
    SourcingManpowerSupplierForm,
    SourcingManpowerContactForm,
    SourcingTradeForm,
    SourcingWorkforceOfferForm,
    SourcingWorkforceOfferVerificationForm,
    SourcingVendorContactForm,
    SourcingVendorForm,
    SourcingVendorOfferForm,
    SourcingVendorOfferVerificationForm,
    SourcingImportUploadForm,
)
from .exchange import (
    EXPORT_DATASETS,
    IMPORT_DATASETS,
    build_export,
    import_sourcing_rows,
    read_import_rows,
)
from .models import (
    SourcingAvailability,
    SourcingEntityStatus,
    SourcingMaterial,
    SourcingManpowerSupplier,
    SourcingManpowerContact,
    SourcingTrade,
    SourcingWorkforceOffer,
    SourcingVendor,
    SourcingVendorContact,
    SourcingVendorOffer,
)
from .selectors.catalog import PAGE_SIZES as HISTORY_PAGE_SIZES, offer_revision_page
from .selectors.material_finder import (
    PAGE_SIZES as FINDER_PAGE_SIZES,
    material_finder_categories,
    material_finder_page,
)
from .selectors.materials import (
    OVERVIEW_PREVIEW_LIMIT as MATERIAL_OVERVIEW_PREVIEW_LIMIT,
    PAGE_SIZES as MATERIAL_PAGE_SIZES,
    material_directory_page,
    vendor_catalog_overview,
    vendor_catalog_page,
)
from .selectors.manpower import PAGE_SIZES as MANPOWER_PAGE_SIZES, manpower_directory_page, manpower_history
from .selectors.trades import PAGE_SIZES as TRADE_PAGE_SIZES, trade_directory_page
from .selectors.workforce import (
    OVERVIEW_PREVIEW_LIMIT as WORKFORCE_OVERVIEW_PREVIEW_LIMIT,
    PAGE_SIZES as WORKFORCE_CATALOG_PAGE_SIZES,
    workforce_catalog_overview,
    workforce_catalog_page,
)
from .selectors.workforce_finder import (
    PAGE_SIZES as WORKFORCE_FINDER_PAGE_SIZES,
    workforce_finder_categories,
    workforce_finder_page,
)
from .selectors.workforce_history import (
    PAGE_SIZES as WORKFORCE_HISTORY_PAGE_SIZES,
    workforce_revision_page,
    workforce_revisions,
)
from .selectors.vendors import PAGE_SIZES, vendor_directory_page, vendor_history
from .services.catalog import (
    create_material,
    create_vendor_offer,
    set_material_active,
    set_vendor_offer_active,
    suggest_material_code,
    update_material,
    update_vendor_offer,
    verify_vendor_offer,
)
from .services.manpower import (
    TRASH_RETENTION_DAYS as MANPOWER_TRASH_RETENTION_DAYS,
    archive_manpower_supplier,
    create_manpower_contact,
    create_manpower_supplier,
    deactivate_manpower_contact,
    restore_manpower_supplier_archive,
    restore_manpower_supplier_trash,
    set_manpower_supplier_status,
    suggest_manpower_supplier_code,
    trash_manpower_supplier,
    update_manpower_contact,
    update_manpower_supplier,
)
from .services.workforce import (
    create_trade,
    create_workforce_offer,
    set_trade_active,
    set_workforce_offer_active,
    suggest_trade_code,
    update_trade,
    update_workforce_offer,
    verify_workforce_offer,
)
from .services.vendors import (
    TRASH_RETENTION_DAYS,
    archive_vendor,
    create_vendor,
    create_vendor_contact,
    deactivate_vendor_contact,
    restore_vendor_archive,
    restore_vendor_trash,
    set_vendor_status,
    suggest_vendor_code,
    trash_vendor,
    update_vendor,
    update_vendor_contact,
)


def _membership(request: HttpRequest):
    return getattr(request, "company_membership", None)


def _require_sourcing(request: HttpRequest) -> None:
    if not membership_has_any_sourcing_access(_membership(request)):
        raise PermissionDenied("Your Access Profile does not include Sourcing Directory access.")


def _require_vendor_view(request: HttpRequest) -> None:
    if not membership_can_view_vendor_sourcing(_membership(request)):
        raise PermissionDenied("Vendor Sourcing view authority is required.")


def _require_vendor_manage(request: HttpRequest) -> None:
    if not membership_can_manage_vendor_sourcing(_membership(request)):
        raise PermissionDenied("Vendor Sourcing edit authority is required.")


def _require_manpower_view(request: HttpRequest) -> None:
    if not membership_can_view_manpower_sourcing(_membership(request)):
        raise PermissionDenied("Manpower Sourcing view authority is required.")


def _require_manpower_manage(request: HttpRequest) -> None:
    if not membership_can_manage_manpower_sourcing(_membership(request)):
        raise PermissionDenied("Manpower Sourcing edit authority is required.")


def _require_master_view(request: HttpRequest) -> None:
    if not membership_can_view_sourcing_masters(_membership(request)):
        raise PermissionDenied("Sourcing Reference Masters view authority is required.")


def _require_master_manage(request: HttpRequest) -> None:
    if not membership_can_manage_sourcing_masters(_membership(request)):
        raise PermissionDenied("Sourcing Reference Masters edit authority is required.")


def _require_data_exchange(request: HttpRequest) -> None:
    membership = _membership(request)
    if not membership or not (
        membership_can_export_sourcing(membership)
        or membership_can_manage_vendor_sourcing(membership)
        or membership_can_manage_manpower_sourcing(membership)
        or membership_can_manage_sourcing_masters(membership)
    ):
        raise PermissionDenied("Sourcing data-exchange access is required.")


def _can_import_dataset(membership, dataset: str) -> bool:
    if dataset in {"vendors", "vendor_catalog"}:
        return membership_can_manage_vendor_sourcing(membership)
    if dataset in {"manpower_suppliers", "workforce_catalog"}:
        return membership_can_manage_manpower_sourcing(membership)
    if dataset in {"materials", "trades"}:
        return membership_can_manage_sourcing_masters(membership)
    return False


def _can_export_dataset(membership, dataset: str) -> bool:
    if not membership_can_export_sourcing(membership):
        return False
    if dataset in {"vendors", "vendor_catalog"}:
        return membership_can_view_vendor_sourcing(membership)
    if dataset in {"manpower_suppliers", "workforce_catalog"}:
        return membership_can_view_manpower_sourcing(membership)
    if dataset in {"materials", "trades"}:
        return membership_can_view_sourcing_masters(membership)
    return False


def _base_context(request: HttpRequest, *, page_key: str, page_title: str, page_subtitle: str = "") -> dict[str, object]:
    return {
        "page_key": page_key,
        "page_title": page_title,
        "page_subtitle": page_subtitle,
        "SOURCING_ACCESS": sourcing_access_context(_membership(request)),
    }




def _safe_sourcing_next(request: HttpRequest, raw: str | None, fallback: str) -> str:
    candidate = str(raw or "").strip()
    if not candidate:
        return fallback
    if not url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return fallback
    sourcing_root = reverse("sourcing:home")
    if not candidate.startswith(sourcing_root):
        return fallback
    return candidate

def _apply_validation_error(form, exc: ValidationError) -> None:
    if hasattr(exc, "message_dict"):
        for field, errors in exc.message_dict.items():
            target = field if field in form.fields else None
            for error in errors:
                form.add_error(target, error)
    else:
        for error in exc.messages:
            form.add_error(None, error)


@login_required
def sourcing_home(request: HttpRequest) -> HttpResponse:
    _require_sourcing(request)
    return render(
        request,
        "sourcing/home.html",
        _base_context(
            request,
            page_key="sourcing-home",
            page_title="Sourcing Directory",
            page_subtitle="Reference-only vendor and manpower sourcing.",
        ),
    )


@login_required
def vendor_list(request: HttpRequest) -> HttpResponse:
    _require_vendor_view(request)
    directory = vendor_directory_page(company=request.company, params=request.GET)
    base_qs = SourcingVendor.objects.for_company(request.company)
    counts = {
        "active": base_qs.filter(deleted_at__isnull=True, archived_at__isnull=True, status=SourcingEntityStatus.ACTIVE).count(),
        "inactive": base_qs.filter(deleted_at__isnull=True, archived_at__isnull=True, status=SourcingEntityStatus.INACTIVE).count(),
        "archived": base_qs.filter(deleted_at__isnull=True, archived_at__isnull=False).count(),
        "trash": base_qs.filter(deleted_at__isnull=False).count(),
    }
    context = _base_context(
        request,
        page_key="sourcing-vendors",
        page_title="Vendors",
        page_subtitle="Reference vendors SESCCO may call for materials. This directory does not create Inventory suppliers or stock.",
    )
    context.update(
        directory=directory,
        page_obj=directory.page_obj,
        vendors=directory.page_obj.object_list,
        counts=counts,
        page_sizes=PAGE_SIZES,
        can_manage=membership_can_manage_vendor_sourcing(_membership(request)),
    )
    return render(request, "sourcing/vendors/list.html", context)


@login_required
def vendor_create(request: HttpRequest) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method == "POST":
        form = SourcingVendorForm(request.POST)
        if form.is_valid():
            try:
                vendor = create_vendor(
                    actor_membership=_membership(request),
                    cleaned_data=form.cleaned_data,
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, f"Vendor {vendor.display_name or vendor.name} was created.")
                return redirect("sourcing:vendor_detail", vendor_id=vendor.pk)
    else:
        form = SourcingVendorForm(initial={"code": suggest_vendor_code()})
    context = _base_context(
        request,
        page_key="sourcing-vendors",
        page_title="New Vendor",
        page_subtitle="Add a reference-only sourcing Vendor. Nothing here creates purchasing, stock or accounting activity.",
    )
    context.update(form=form, submit_label="Create Vendor", cancel_url="sourcing:vendor_list")
    return render(request, "sourcing/vendors/form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def vendor_detail(request: HttpRequest, vendor_id) -> HttpResponse:
    _require_vendor_view(request)
    vendor = get_object_or_404(SourcingVendor.objects.for_company(request.company), pk=vendor_id)
    contacts = list(vendor.contacts.order_by("-is_active", "-is_primary", "first_name", "last_name"))
    catalog_page_obj, catalog, catalog_page_size = vendor_catalog_page(
        company=request.company,
        vendor=vendor,
        page=request.GET.get("catalog_page", 1),
        page_size=request.GET.get("catalog_page_size", 25),
    )
    catalog_overview = (
        catalog[:MATERIAL_OVERVIEW_PREVIEW_LIMIT]
        if catalog_page_obj.number == 1
        else vendor_catalog_overview(company=request.company, vendor=vendor)
    )
    catalog_total_count = catalog_page_obj.paginator.count
    context = _base_context(
        request,
        page_key="sourcing-vendors",
        page_title=vendor.display_name or vendor.name,
        page_subtitle=f"{vendor.code} · Vendor Sourcing reference profile",
    )
    context.update(
        vendor=vendor,
        contacts=contacts,
        active_contacts=[item for item in contacts if item.is_active],
        contact_form=SourcingVendorContactForm(),
        catalog=catalog,
        catalog_overview=catalog_overview,
        catalog_total_count=catalog_total_count,
        catalog_overview_has_more=catalog_total_count > len(catalog_overview),
        active_catalog_count=vendor.supply_offers.filter(is_active=True).count(),
        catalog_page_obj=catalog_page_obj,
        catalog_page_size=catalog_page_size,
        catalog_page_sizes=MATERIAL_PAGE_SIZES,
        history=vendor_history(company=request.company, vendor=vendor),
        can_manage=membership_can_manage_vendor_sourcing(_membership(request)),
        retention_days=TRASH_RETENTION_DAYS,
    )
    return render(request, "sourcing/vendors/detail.html", context)


@login_required
def vendor_edit(request: HttpRequest, vendor_id) -> HttpResponse:
    _require_vendor_manage(request)
    vendor = get_object_or_404(
        SourcingVendor.objects.for_company(request.company).filter(deleted_at__isnull=True),
        pk=vendor_id,
    )
    if vendor.archived_at:
        messages.error(request, "Restore this Vendor before editing its master data.")
        return redirect("sourcing:vendor_detail", vendor_id=vendor.pk)
    if request.method == "POST":
        form = SourcingVendorForm(request.POST, instance=vendor)
        if form.is_valid():
            try:
                vendor = update_vendor(
                    actor_membership=_membership(request),
                    vendor_id=vendor.pk,
                    cleaned_data=form.cleaned_data,
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Vendor details were updated.")
                return redirect("sourcing:vendor_detail", vendor_id=vendor.pk)
    else:
        form = SourcingVendorForm(instance=vendor)
    context = _base_context(
        request,
        page_key="sourcing-vendors",
        page_title="Edit Vendor",
        page_subtitle=f"Update {vendor.display_name or vendor.name} sourcing reference details.",
    )
    context.update(form=form, vendor=vendor, submit_label="Save Vendor")
    return render(request, "sourcing/vendors/form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def vendor_status(request: HttpRequest, vendor_id) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Vendor status changes require POST.")
    try:
        vendor = set_vendor_status(
            actor_membership=_membership(request),
            vendor_id=vendor_id,
            status=str(request.POST.get("status") or ""),
            request=request,
        )
    except (ValidationError, SourcingVendor.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        return redirect("sourcing:vendor_detail", vendor_id=vendor_id)
    messages.success(request, f"Vendor status changed to {vendor.get_status_display()}.")
    return redirect("sourcing:vendor_detail", vendor_id=vendor.pk)


@login_required
def vendor_archive(request: HttpRequest, vendor_id) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Vendor archive actions require POST.")
    try:
        vendor = archive_vendor(
            actor_membership=_membership(request),
            vendor_id=vendor_id,
            reason=request.POST.get("reason", ""),
            request=request,
        )
    except (ValidationError, SourcingVendor.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, f"{vendor.display_name or vendor.name} was archived.")
    return redirect("sourcing:vendor_detail", vendor_id=vendor_id)


@login_required
def vendor_restore_archive(request: HttpRequest, vendor_id) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Vendor restore actions require POST.")
    try:
        vendor = restore_vendor_archive(actor_membership=_membership(request), vendor_id=vendor_id, request=request)
    except SourcingVendor.DoesNotExist:
        messages.error(request, "Vendor was not found.")
    else:
        messages.success(request, f"{vendor.display_name or vendor.name} was restored from Archive.")
    return redirect("sourcing:vendor_detail", vendor_id=vendor_id)


@login_required
def vendor_trash(request: HttpRequest, vendor_id) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Vendor delete actions require POST.")
    try:
        vendor = trash_vendor(
            actor_membership=_membership(request),
            vendor_id=vendor_id,
            confirmation=request.POST.get("confirmation", ""),
            reason=request.POST.get("reason", ""),
            request=request,
        )
    except (ValidationError, SourcingVendor.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        return redirect("sourcing:vendor_detail", vendor_id=vendor_id)
    messages.success(request, f"{vendor.display_name or vendor.name} was moved to Trash for {TRASH_RETENTION_DAYS} days.")
    return redirect("sourcing:vendor_list")


@login_required
def vendor_restore_trash(request: HttpRequest, vendor_id) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Vendor restore actions require POST.")
    try:
        vendor = restore_vendor_trash(actor_membership=_membership(request), vendor_id=vendor_id, request=request)
    except SourcingVendor.DoesNotExist:
        messages.error(request, "Vendor Trash record was not found.")
        return redirect("sourcing:vendor_list")
    messages.success(request, f"{vendor.display_name or vendor.name} was restored from Trash.")
    return redirect("sourcing:vendor_detail", vendor_id=vendor.pk)


@login_required
def vendor_contact_create(request: HttpRequest, vendor_id) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Vendor contact creation requires POST.")
    vendor = get_object_or_404(
        SourcingVendor.objects.for_company(request.company).filter(deleted_at__isnull=True, archived_at__isnull=True),
        pk=vendor_id,
    )
    form = SourcingVendorContactForm(request.POST)
    if form.is_valid():
        try:
            create_vendor_contact(
                actor_membership=_membership(request),
                vendor_id=vendor.pk,
                cleaned_data=form.cleaned_data,
                request=request,
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Vendor contact was added.")
    else:
        messages.error(request, "Contact was not saved. Check the required fields and email format.")
    return redirect("sourcing:vendor_detail", vendor_id=vendor.pk)


@login_required
def vendor_contact_edit(request: HttpRequest, vendor_id, contact_id) -> HttpResponse:
    _require_vendor_manage(request)
    vendor = get_object_or_404(
        SourcingVendor.objects.for_company(request.company).filter(deleted_at__isnull=True, archived_at__isnull=True),
        pk=vendor_id,
    )
    contact = get_object_or_404(SourcingVendorContact.objects.for_company(request.company), pk=contact_id, vendor=vendor)
    if request.method == "POST":
        form = SourcingVendorContactForm(request.POST, instance=contact)
        if form.is_valid():
            try:
                update_vendor_contact(
                    actor_membership=_membership(request),
                    vendor_id=vendor.pk,
                    contact_id=contact.pk,
                    cleaned_data=form.cleaned_data,
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Vendor contact was updated.")
                return redirect("sourcing:vendor_detail", vendor_id=vendor.pk)
    else:
        form = SourcingVendorContactForm(instance=contact)
    context = _base_context(
        request,
        page_key="sourcing-vendors",
        page_title="Edit Contact",
        page_subtitle=f"{vendor.display_name or vendor.name} · {contact.full_name}",
    )
    context.update(vendor=vendor, contact=contact, form=form)
    return render(request, "sourcing/vendors/contact_form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def vendor_contact_deactivate(request: HttpRequest, vendor_id, contact_id) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Vendor contact deactivation requires POST.")
    try:
        deactivate_vendor_contact(
            actor_membership=_membership(request),
            vendor_id=vendor_id,
            contact_id=contact_id,
            request=request,
        )
    except (ValidationError, SourcingVendor.DoesNotExist, SourcingVendorContact.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, "Vendor contact was deactivated.")
    return redirect("sourcing:vendor_detail", vendor_id=vendor_id)


@login_required
def manpower_supplier_list(request: HttpRequest) -> HttpResponse:
    _require_manpower_view(request)
    directory = manpower_directory_page(company=request.company, params=request.GET)
    base_qs = SourcingManpowerSupplier.objects.for_company(request.company)
    counts = {
        "active": base_qs.filter(deleted_at__isnull=True, archived_at__isnull=True, status=SourcingEntityStatus.ACTIVE).count(),
        "inactive": base_qs.filter(deleted_at__isnull=True, archived_at__isnull=True, status=SourcingEntityStatus.INACTIVE).count(),
        "archived": base_qs.filter(deleted_at__isnull=True, archived_at__isnull=False).count(),
        "trash": base_qs.filter(deleted_at__isnull=False).count(),
    }
    context = _base_context(
        request,
        page_key="sourcing-manpower",
        page_title="Manpower Suppliers",
        page_subtitle="Reference manpower companies SESCCO may call on demand. This directory does not create Rental Payroll suppliers or workers.",
    )
    context.update(
        directory=directory,
        page_obj=directory.page_obj,
        suppliers=directory.page_obj.object_list,
        counts=counts,
        page_sizes=MANPOWER_PAGE_SIZES,
        can_manage=membership_can_manage_manpower_sourcing(_membership(request)),
    )
    return render(request, "sourcing/manpower/list.html", context)


@login_required
def manpower_supplier_create(request: HttpRequest) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method == "POST":
        form = SourcingManpowerSupplierForm(request.POST)
        if form.is_valid():
            try:
                supplier = create_manpower_supplier(
                    actor_membership=_membership(request),
                    cleaned_data=form.cleaned_data,
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, f"Manpower Supplier {supplier.name} was created.")
                return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier.pk)
    else:
        form = SourcingManpowerSupplierForm(initial={"code": suggest_manpower_supplier_code()})
    context = _base_context(
        request,
        page_key="sourcing-manpower",
        page_title="New Manpower Supplier",
        page_subtitle="Add a reference-only source SESCCO may call for workers. Nothing here creates Rental Payroll suppliers, workers or assignments.",
    )
    context.update(form=form, submit_label="Create Manpower Supplier")
    return render(request, "sourcing/manpower/form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def manpower_supplier_detail(request: HttpRequest, supplier_id) -> HttpResponse:
    _require_manpower_view(request)
    supplier = get_object_or_404(SourcingManpowerSupplier.objects.for_company(request.company), pk=supplier_id)
    contacts = list(supplier.contacts.order_by("-is_active", "-is_primary", "first_name", "last_name"))
    workforce_page_obj, workforce, workforce_page_size = workforce_catalog_page(
        company=request.company,
        supplier=supplier,
        page=request.GET.get("workforce_page", 1),
        page_size=request.GET.get("workforce_page_size", 25),
    )
    workforce_overview = (
        workforce[:WORKFORCE_OVERVIEW_PREVIEW_LIMIT]
        if workforce_page_obj.number == 1
        else workforce_catalog_overview(company=request.company, supplier=supplier)
    )
    workforce_total_count = workforce_page_obj.paginator.count
    workforce_count = supplier.workforce_offers.filter(is_active=True).count()
    context = _base_context(
        request,
        page_key="sourcing-manpower",
        page_title=supplier.name,
        page_subtitle=f"{supplier.code} · Manpower Sourcing reference profile",
    )
    context.update(
        supplier=supplier,
        contacts=contacts,
        active_contacts=[item for item in contacts if item.is_active],
        contact_form=SourcingManpowerContactForm(),
        workforce=workforce,
        workforce_overview=workforce_overview,
        workforce_total_count=workforce_total_count,
        workforce_overview_has_more=workforce_total_count > len(workforce_overview),
        workforce_count=workforce_count,
        workforce_page_obj=workforce_page_obj,
        workforce_page_size=workforce_page_size,
        workforce_page_sizes=WORKFORCE_CATALOG_PAGE_SIZES,
        history=manpower_history(company=request.company, supplier=supplier),
        can_manage=membership_can_manage_manpower_sourcing(_membership(request)),
        retention_days=MANPOWER_TRASH_RETENTION_DAYS,
    )
    return render(request, "sourcing/manpower/detail.html", context)


@login_required
def manpower_supplier_edit(request: HttpRequest, supplier_id) -> HttpResponse:
    _require_manpower_manage(request)
    supplier = get_object_or_404(
        SourcingManpowerSupplier.objects.for_company(request.company).filter(deleted_at__isnull=True),
        pk=supplier_id,
    )
    if supplier.archived_at:
        messages.error(request, "Restore this Manpower Supplier before editing its master data.")
        return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier.pk)
    if request.method == "POST":
        form = SourcingManpowerSupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            try:
                supplier = update_manpower_supplier(
                    actor_membership=_membership(request),
                    supplier_id=supplier.pk,
                    cleaned_data=form.cleaned_data,
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Manpower Supplier details were updated.")
                return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier.pk)
    else:
        form = SourcingManpowerSupplierForm(instance=supplier)
    context = _base_context(
        request,
        page_key="sourcing-manpower",
        page_title="Edit Manpower Supplier",
        page_subtitle=f"Update {supplier.name} sourcing reference details.",
    )
    context.update(form=form, supplier=supplier, submit_label="Save Manpower Supplier")
    return render(request, "sourcing/manpower/form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def manpower_supplier_status(request: HttpRequest, supplier_id) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Manpower Supplier status changes require POST.")
    try:
        supplier = set_manpower_supplier_status(
            actor_membership=_membership(request),
            supplier_id=supplier_id,
            status=str(request.POST.get("status") or ""),
            request=request,
        )
    except (ValidationError, SourcingManpowerSupplier.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier_id)
    messages.success(request, f"Manpower Supplier status changed to {supplier.get_status_display()}.")
    return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier.pk)


@login_required
def manpower_supplier_archive(request: HttpRequest, supplier_id) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Manpower Supplier archive actions require POST.")
    try:
        supplier = archive_manpower_supplier(
            actor_membership=_membership(request),
            supplier_id=supplier_id,
            reason=request.POST.get("reason", ""),
            request=request,
        )
    except (ValidationError, SourcingManpowerSupplier.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, f"{supplier.name} was archived.")
    return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier_id)


@login_required
def manpower_supplier_restore_archive(request: HttpRequest, supplier_id) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Manpower Supplier restore actions require POST.")
    try:
        supplier = restore_manpower_supplier_archive(actor_membership=_membership(request), supplier_id=supplier_id, request=request)
    except SourcingManpowerSupplier.DoesNotExist:
        messages.error(request, "Manpower Supplier was not found.")
    else:
        messages.success(request, f"{supplier.name} was restored from Archive.")
    return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier_id)


@login_required
def manpower_supplier_trash(request: HttpRequest, supplier_id) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Manpower Supplier delete actions require POST.")
    try:
        supplier = trash_manpower_supplier(
            actor_membership=_membership(request),
            supplier_id=supplier_id,
            confirmation=request.POST.get("confirmation", ""),
            reason=request.POST.get("reason", ""),
            request=request,
        )
    except (ValidationError, SourcingManpowerSupplier.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier_id)
    messages.success(request, f"{supplier.name} was moved to Trash for {MANPOWER_TRASH_RETENTION_DAYS} days.")
    return redirect("sourcing:manpower_supplier_list")


@login_required
def manpower_supplier_restore_trash(request: HttpRequest, supplier_id) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Manpower Supplier restore actions require POST.")
    try:
        supplier = restore_manpower_supplier_trash(actor_membership=_membership(request), supplier_id=supplier_id, request=request)
    except SourcingManpowerSupplier.DoesNotExist:
        messages.error(request, "Manpower Supplier Trash record was not found.")
        return redirect("sourcing:manpower_supplier_list")
    messages.success(request, f"{supplier.name} was restored from Trash.")
    return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier.pk)


@login_required
def manpower_contact_create(request: HttpRequest, supplier_id) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Manpower contact creation requires POST.")
    supplier = get_object_or_404(
        SourcingManpowerSupplier.objects.for_company(request.company).filter(deleted_at__isnull=True, archived_at__isnull=True),
        pk=supplier_id,
    )
    form = SourcingManpowerContactForm(request.POST)
    if form.is_valid():
        try:
            create_manpower_contact(
                actor_membership=_membership(request),
                supplier_id=supplier.pk,
                cleaned_data=form.cleaned_data,
                request=request,
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Manpower Supplier contact was added.")
    else:
        messages.error(request, "Contact was not saved. Check the required fields and email format.")
    return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier.pk)


@login_required
def manpower_contact_edit(request: HttpRequest, supplier_id, contact_id) -> HttpResponse:
    _require_manpower_manage(request)
    supplier = get_object_or_404(
        SourcingManpowerSupplier.objects.for_company(request.company).filter(deleted_at__isnull=True, archived_at__isnull=True),
        pk=supplier_id,
    )
    contact = get_object_or_404(SourcingManpowerContact.objects.for_company(request.company), pk=contact_id, supplier=supplier)
    if request.method == "POST":
        form = SourcingManpowerContactForm(request.POST, instance=contact)
        if form.is_valid():
            try:
                update_manpower_contact(
                    actor_membership=_membership(request),
                    supplier_id=supplier.pk,
                    contact_id=contact.pk,
                    cleaned_data=form.cleaned_data,
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Manpower Supplier contact was updated.")
                return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier.pk)
    else:
        form = SourcingManpowerContactForm(instance=contact)
    context = _base_context(
        request,
        page_key="sourcing-manpower",
        page_title="Edit Contact",
        page_subtitle=f"{supplier.name} · {contact.full_name}",
    )
    context.update(supplier=supplier, contact=contact, form=form)
    return render(request, "sourcing/manpower/contact_form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def manpower_contact_deactivate(request: HttpRequest, supplier_id, contact_id) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Manpower contact deactivation requires POST.")
    try:
        deactivate_manpower_contact(
            actor_membership=_membership(request),
            supplier_id=supplier_id,
            contact_id=contact_id,
            request=request,
        )
    except (ValidationError, SourcingManpowerSupplier.DoesNotExist, SourcingManpowerContact.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, "Manpower Supplier contact was deactivated.")
    return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier_id)


@login_required
def workforce_offer_create(request: HttpRequest, supplier_id) -> HttpResponse:
    _require_manpower_manage(request)
    supplier = get_object_or_404(
        SourcingManpowerSupplier.objects.for_company(request.company).filter(deleted_at__isnull=True, archived_at__isnull=True),
        pk=supplier_id,
    )
    if request.method == "POST":
        form = SourcingWorkforceOfferForm(request.POST, company=request.company, supplier=supplier)
        if form.is_valid():
            try:
                create_workforce_offer(
                    actor_membership=_membership(request),
                    supplier_id=supplier.pk,
                    cleaned_data={key: value for key, value in form.cleaned_data.items() if key not in {"verified_now", "contact_name"}},
                    verified_now=bool(form.cleaned_data.get("verified_now")),
                    contact_name=str(form.cleaned_data.get("contact_name") or ""),
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Workforce capability was added.")
                return redirect(f"{reverse('sourcing:manpower_supplier_detail', args=[supplier.pk])}#workforce")
    else:
        form = SourcingWorkforceOfferForm(company=request.company, supplier=supplier)
    context = _base_context(
        request,
        page_key="sourcing-manpower",
        page_title="Add Workforce Capability",
        page_subtitle=f"Add a reference worker type for {supplier.name}.",
    )
    context.update(form=form, supplier=supplier, submit_label="Add Workforce Capability")
    return render(request, "sourcing/manpower/workforce_form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def workforce_offer_edit(request: HttpRequest, supplier_id, offer_id) -> HttpResponse:
    _require_manpower_manage(request)
    supplier = get_object_or_404(
        SourcingManpowerSupplier.objects.for_company(request.company).filter(deleted_at__isnull=True, archived_at__isnull=True),
        pk=supplier_id,
    )
    offer = get_object_or_404(
        SourcingWorkforceOffer.objects.for_company(request.company).select_related("trade", "supplier"),
        pk=offer_id,
        supplier=supplier,
    )
    if request.method == "POST":
        form = SourcingWorkforceOfferForm(request.POST, instance=offer, company=request.company, supplier=supplier)
        if form.is_valid():
            try:
                update_workforce_offer(
                    actor_membership=_membership(request),
                    supplier_id=supplier.pk,
                    offer_id=offer.pk,
                    cleaned_data={key: value for key, value in form.cleaned_data.items() if key not in {"verified_now", "contact_name"}},
                    verified_now=bool(form.cleaned_data.get("verified_now")),
                    contact_name=str(form.cleaned_data.get("contact_name") or ""),
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Workforce capability was updated.")
                return redirect(f"{reverse('sourcing:manpower_supplier_detail', args=[supplier.pk])}#workforce")
    else:
        form = SourcingWorkforceOfferForm(instance=offer, company=request.company, supplier=supplier)
    context = _base_context(
        request,
        page_key="sourcing-manpower",
        page_title="Edit Workforce Capability",
        page_subtitle=f"{supplier.name} · {offer.trade.name}",
    )
    context.update(form=form, supplier=supplier, offer=offer, submit_label="Save Workforce Capability")
    return render(request, "sourcing/manpower/workforce_form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def workforce_offer_status(request: HttpRequest, supplier_id, offer_id) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Workforce Catalog status changes require POST.")
    is_active = str(request.POST.get("active") or "").lower() in {"1", "true", "yes", "active"}
    try:
        set_workforce_offer_active(
            actor_membership=_membership(request),
            supplier_id=supplier_id,
            offer_id=offer_id,
            is_active=is_active,
            request=request,
        )
    except (ValidationError, SourcingManpowerSupplier.DoesNotExist, SourcingWorkforceOffer.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, "Workforce capability status was updated.")
    return redirect(f"{reverse('sourcing:manpower_supplier_detail', args=[supplier_id])}#workforce")


@login_required
def workforce_offer_verify(request: HttpRequest, supplier_id, offer_id) -> HttpResponse:
    _require_manpower_manage(request)
    supplier = get_object_or_404(
        SourcingManpowerSupplier.objects.for_company(request.company), pk=supplier_id
    )
    offer = get_object_or_404(
        SourcingWorkforceOffer.objects.for_company(request.company).select_related("trade", "supplier", "verified_by"),
        pk=offer_id, supplier=supplier,
    )
    fallback = f"{reverse('sourcing:manpower_supplier_detail', args=[supplier.pk])}#workforce"
    next_url = _safe_sourcing_next(request, request.POST.get("next") if request.method == "POST" else request.GET.get("next"), fallback)
    if supplier.deleted_at or supplier.archived_at or not offer.is_active:
        messages.error(request, "Restore/reactivate this sourcing reference before verifying it.")
        return redirect(next_url)

    if request.method == "POST":
        form = SourcingWorkforceOfferVerificationForm(request.POST, instance=offer, supplier=supplier)
        if form.is_valid():
            cleaned = {key: value for key, value in form.cleaned_data.items() if key != "contact_name"}
            try:
                verify_workforce_offer(
                    actor_membership=_membership(request),
                    supplier_id=supplier.pk,
                    offer_id=offer.pk,
                    cleaned_data=cleaned,
                    contact_name=form.cleaned_data.get("contact_name", ""),
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, f"{offer.trade.name} workforce reference was verified.")
                return redirect(next_url)
    else:
        form = SourcingWorkforceOfferVerificationForm(instance=offer, supplier=supplier)

    context = _base_context(
        request,
        page_key="sourcing-workforce-finder",
        page_title="Verify Workforce Reference",
        page_subtitle=f"{supplier.name} · {offer.trade.name}",
    )
    context.update(
        form=form, supplier=supplier, offer=offer, next_url=next_url,
        recent_history=workforce_revisions(company=request.company, offer=offer, limit=5),
    )
    return render(request, "sourcing/manpower/workforce_verify.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def workforce_offer_history(request: HttpRequest, supplier_id, offer_id) -> HttpResponse:
    _require_manpower_view(request)
    supplier = get_object_or_404(
        SourcingManpowerSupplier.objects.for_company(request.company), pk=supplier_id
    )
    offer = get_object_or_404(
        SourcingWorkforceOffer.objects.for_company(request.company).select_related("trade", "supplier", "verified_by"),
        pk=offer_id, supplier=supplier,
    )
    fallback = f"{reverse('sourcing:manpower_supplier_detail', args=[supplier.pk])}#workforce"
    next_url = _safe_sourcing_next(request, request.GET.get("next"), fallback)
    page_obj, entries, page_size = workforce_revision_page(
        company=request.company,
        offer=offer,
        page=request.GET.get("page", 1),
        page_size=request.GET.get("page_size", 25),
    )
    context = _base_context(
        request,
        page_key="sourcing-workforce-finder",
        page_title="Workforce Verification History",
        page_subtitle=f"{supplier.name} · {offer.trade.name}",
    )
    context.update(
        supplier=supplier, offer=offer, next_url=next_url, page_obj=page_obj, entries=entries,
        page_size=page_size, page_sizes=WORKFORCE_HISTORY_PAGE_SIZES,
        can_manage=membership_can_manage_manpower_sourcing(_membership(request)),
    )
    return render(request, "sourcing/manpower/workforce_history.html", context)


@login_required
def material_finder(request: HttpRequest) -> HttpResponse:
    _require_vendor_view(request)
    finder = material_finder_page(company=request.company, params=request.GET)
    context = _base_context(
        request,
        page_key="sourcing-material-finder",
        page_title="Material Finder",
        page_subtitle="Find which reference Vendors can supply a material and compare last-known quantity, rate, lead time and verification freshness.",
    )
    context.update(
        finder=finder,
        page_obj=finder.page_obj,
        offers=finder.page_obj.object_list,
        page_sizes=FINDER_PAGE_SIZES,
        availability_choices=SourcingAvailability.choices,
        categories=material_finder_categories(company=request.company),
        can_manage=membership_can_manage_vendor_sourcing(_membership(request)),
    )
    return render(request, "sourcing/material_finder/list.html", context)


@login_required
def workforce_finder(request: HttpRequest) -> HttpResponse:
    _require_manpower_view(request)
    finder = workforce_finder_page(company=request.company, params=request.GET)
    context = _base_context(
        request,
        page_key="sourcing-workforce-finder",
        page_title="Workforce Finder",
        page_subtitle="Find which reference Manpower Suppliers can provide a worker type and compare last-known quantity, rate, mobilization and verification freshness.",
    )
    context.update(
        finder=finder,
        page_obj=finder.page_obj,
        offers=finder.page_obj.object_list,
        page_sizes=WORKFORCE_FINDER_PAGE_SIZES,
        availability_choices=SourcingAvailability.choices,
        categories=workforce_finder_categories(company=request.company),
        can_manage=membership_can_manage_manpower_sourcing(_membership(request)),
    )
    return render(request, "sourcing/workforce_finder/list.html", context)


@login_required
def material_list(request: HttpRequest) -> HttpResponse:
    _require_master_view(request)
    directory = material_directory_page(company=request.company, params=request.GET)
    base_qs = SourcingMaterial.objects.for_company(request.company)
    context = _base_context(
        request,
        page_key="sourcing-materials",
        page_title="Sourcing Materials",
        page_subtitle="Controlled reference items and aliases used only by the Sourcing Directory.",
    )
    context.update(
        directory=directory,
        page_obj=directory.page_obj,
        materials=directory.page_obj.object_list,
        page_sizes=MATERIAL_PAGE_SIZES,
        counts={
            "active": base_qs.filter(is_active=True).count(),
            "inactive": base_qs.filter(is_active=False).count(),
        },
        can_manage=membership_can_manage_sourcing_masters(_membership(request)),
    )
    return render(request, "sourcing/materials/list.html", context)


@login_required
def material_create(request: HttpRequest) -> HttpResponse:
    _require_master_manage(request)
    if request.method == "POST":
        form = SourcingMaterialForm(request.POST)
        if form.is_valid():
            try:
                material = create_material(
                    actor_membership=_membership(request),
                    cleaned_data=form.cleaned_data,
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, f"Sourcing Material {material.name} was created.")
                return redirect("sourcing:material_list")
    else:
        form = SourcingMaterialForm(initial={"code": suggest_material_code()})
    context = _base_context(
        request,
        page_key="sourcing-materials",
        page_title="New Sourcing Material",
        page_subtitle="Create a controlled Sourcing reference item. This does not create Inventory stock or an Inventory item.",
    )
    context.update(form=form, submit_label="Create Material")
    return render(request, "sourcing/materials/form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def material_edit(request: HttpRequest, material_id) -> HttpResponse:
    _require_master_manage(request)
    material = get_object_or_404(SourcingMaterial.objects.for_company(request.company), pk=material_id)
    if request.method == "POST":
        form = SourcingMaterialForm(request.POST, instance=material)
        if form.is_valid():
            try:
                material = update_material(
                    actor_membership=_membership(request),
                    material_id=material.pk,
                    cleaned_data=form.cleaned_data,
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Sourcing Material was updated.")
                return redirect("sourcing:material_list")
    else:
        form = SourcingMaterialForm(instance=material)
    context = _base_context(
        request,
        page_key="sourcing-materials",
        page_title="Edit Sourcing Material",
        page_subtitle=f"Update {material.code} · {material.name}.",
    )
    context.update(form=form, material=material, submit_label="Save Material")
    return render(request, "sourcing/materials/form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def material_status(request: HttpRequest, material_id) -> HttpResponse:
    _require_master_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Material status changes require POST.")
    is_active = str(request.POST.get("active") or "").lower() in {"1", "true", "yes", "active"}
    try:
        material = set_material_active(
            actor_membership=_membership(request),
            material_id=material_id,
            is_active=is_active,
            request=request,
        )
    except (ValidationError, SourcingMaterial.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, f"{material.name} is now {'Active' if material.is_active else 'Inactive'}.")
    return redirect("sourcing:material_list")



@login_required
def trade_list(request: HttpRequest) -> HttpResponse:
    _require_master_view(request)
    directory = trade_directory_page(company=request.company, params=request.GET)
    base_qs = SourcingTrade.objects.for_company(request.company)
    context = _base_context(
        request,
        page_key="sourcing-trades",
        page_title="Worker Types / Trades",
        page_subtitle="Controlled sourcing-only worker terminology used for manpower capability tracking.",
    )
    context.update(
        directory=directory,
        page_obj=directory.page_obj,
        trades=directory.page_obj.object_list,
        page_sizes=TRADE_PAGE_SIZES,
        counts={
            "active": base_qs.filter(is_active=True).count(),
            "inactive": base_qs.filter(is_active=False).count(),
        },
        can_manage=membership_can_manage_sourcing_masters(_membership(request)),
    )
    return render(request, "sourcing/trades/list.html", context)


@login_required
def trade_create(request: HttpRequest) -> HttpResponse:
    _require_master_manage(request)
    if request.method == "POST":
        form = SourcingTradeForm(request.POST)
        if form.is_valid():
            try:
                trade = create_trade(actor_membership=_membership(request), cleaned_data=form.cleaned_data, request=request)
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, f"Sourcing Trade {trade.name} was created.")
                return redirect("sourcing:trade_list")
    else:
        form = SourcingTradeForm(initial={"code": suggest_trade_code()})
    context = _base_context(
        request,
        page_key="sourcing-trades",
        page_title="New Worker Type / Trade",
        page_subtitle="Create controlled worker terminology for sourcing. This does not create Payroll workers or occupations.",
    )
    context.update(form=form, submit_label="Create Trade")
    return render(request, "sourcing/trades/form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def trade_edit(request: HttpRequest, trade_id) -> HttpResponse:
    _require_master_manage(request)
    trade = get_object_or_404(SourcingTrade.objects.for_company(request.company), pk=trade_id)
    if request.method == "POST":
        form = SourcingTradeForm(request.POST, instance=trade)
        if form.is_valid():
            try:
                trade = update_trade(
                    actor_membership=_membership(request), trade_id=trade.pk, cleaned_data=form.cleaned_data, request=request
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Sourcing Trade was updated.")
                return redirect("sourcing:trade_list")
    else:
        form = SourcingTradeForm(instance=trade)
    context = _base_context(
        request,
        page_key="sourcing-trades",
        page_title="Edit Worker Type / Trade",
        page_subtitle=f"Update {trade.code} · {trade.name}.",
    )
    context.update(form=form, trade=trade, submit_label="Save Trade")
    return render(request, "sourcing/trades/form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def trade_status(request: HttpRequest, trade_id) -> HttpResponse:
    _require_master_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Trade status changes require POST.")
    is_active = str(request.POST.get("active") or "").lower() in {"1", "true", "yes", "active"}
    try:
        trade = set_trade_active(
            actor_membership=_membership(request), trade_id=trade_id, is_active=is_active, request=request
        )
    except (ValidationError, SourcingTrade.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, f"{trade.name} is now {'Active' if trade.is_active else 'Inactive'}.")
    return redirect("sourcing:trade_list")


@login_required
def vendor_offer_verify(request: HttpRequest, vendor_id, offer_id) -> HttpResponse:
    _require_vendor_manage(request)
    vendor = get_object_or_404(
        SourcingVendor.objects.for_company(request.company).filter(deleted_at__isnull=True, archived_at__isnull=True),
        pk=vendor_id,
    )
    offer = get_object_or_404(
        SourcingVendorOffer.objects.for_company(request.company).select_related("material", "vendor", "verified_by"),
        pk=offer_id,
        vendor=vendor,
    )
    if not offer.is_active:
        messages.error(request, "Reactivate this Supply Catalog item before verifying it.")
        return redirect(f"{reverse('sourcing:vendor_detail', args=[vendor.pk])}#catalog")

    fallback = f"{reverse('sourcing:vendor_detail', args=[vendor.pk])}#catalog"
    next_url = _safe_sourcing_next(request, request.POST.get("next") if request.method == "POST" else request.GET.get("next"), fallback)
    if request.method == "POST":
        form = SourcingVendorOfferVerificationForm(request.POST, instance=offer, vendor=vendor)
        if form.is_valid():
            try:
                verify_vendor_offer(
                    actor_membership=_membership(request),
                    vendor_id=vendor.pk,
                    offer_id=offer.pk,
                    cleaned_data={key: value for key, value in form.cleaned_data.items() if key != "contact_name"},
                    contact_name=str(form.cleaned_data.get("contact_name") or ""),
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Supply reference was verified and its previous values were preserved in history.")
                return redirect(next_url)
    else:
        form = SourcingVendorOfferVerificationForm(instance=offer, vendor=vendor)

    page_obj, history, _size = offer_revision_page(company=request.company, offer=offer, page=1, page_size=5)
    context = _base_context(
        request,
        page_key="sourcing-vendors",
        page_title="Verify Supply Reference",
        page_subtitle=f"{vendor.display_name or vendor.name} · {offer.material.name}",
    )
    context.update(
        vendor=vendor,
        offer=offer,
        form=form,
        next_url=next_url,
        recent_history=history,
        history_total=page_obj.paginator.count,
    )
    return render(request, "sourcing/vendors/offer_verify.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def vendor_offer_history(request: HttpRequest, vendor_id, offer_id) -> HttpResponse:
    _require_vendor_view(request)
    vendor = get_object_or_404(
        SourcingVendor.objects.for_company(request.company),
        pk=vendor_id,
    )
    offer = get_object_or_404(
        SourcingVendorOffer.objects.for_company(request.company).select_related("material", "vendor", "verified_by"),
        pk=offer_id,
        vendor=vendor,
    )
    page_obj, entries, page_size = offer_revision_page(
        company=request.company,
        offer=offer,
        page=request.GET.get("page") or 1,
        page_size=request.GET.get("page_size") or 25,
    )
    fallback = f"{reverse('sourcing:vendor_detail', args=[vendor.pk])}#catalog"
    next_url = _safe_sourcing_next(request, request.GET.get("next"), fallback)
    context = _base_context(
        request,
        page_key="sourcing-vendors",
        page_title="Verification History",
        page_subtitle=f"{vendor.display_name or vendor.name} · {offer.material.name}",
    )
    context.update(
        vendor=vendor,
        offer=offer,
        entries=entries,
        page_obj=page_obj,
        page_size=page_size,
        page_sizes=HISTORY_PAGE_SIZES,
        next_url=next_url,
        can_manage=membership_can_manage_vendor_sourcing(_membership(request)),
    )
    return render(request, "sourcing/vendors/offer_history.html", context)


@login_required
def vendor_offer_create(request: HttpRequest, vendor_id) -> HttpResponse:
    _require_vendor_manage(request)
    vendor = get_object_or_404(
        SourcingVendor.objects.for_company(request.company).filter(deleted_at__isnull=True, archived_at__isnull=True),
        pk=vendor_id,
    )
    if request.method == "POST":
        form = SourcingVendorOfferForm(request.POST, company=request.company)
        if form.is_valid():
            try:
                create_vendor_offer(
                    actor_membership=_membership(request),
                    vendor_id=vendor.pk,
                    cleaned_data={key: value for key, value in form.cleaned_data.items() if key not in {"verified_now", "contact_name"}},
                    verified_now=bool(form.cleaned_data.get("verified_now")),
                    contact_name=str(form.cleaned_data.get("contact_name") or ""),
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Supply Catalog item was added.")
                return redirect(f"{reverse('sourcing:vendor_detail', args=[vendor.pk])}#catalog")
    else:
        form = SourcingVendorOfferForm(company=request.company)
    context = _base_context(
        request,
        page_key="sourcing-vendors",
        page_title="Add Supply Item",
        page_subtitle=f"Add a reference material capability for {vendor.display_name or vendor.name}.",
    )
    context.update(form=form, vendor=vendor, submit_label="Add Supply Item")
    return render(request, "sourcing/vendors/offer_form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def vendor_offer_edit(request: HttpRequest, vendor_id, offer_id) -> HttpResponse:
    _require_vendor_manage(request)
    vendor = get_object_or_404(
        SourcingVendor.objects.for_company(request.company).filter(deleted_at__isnull=True, archived_at__isnull=True),
        pk=vendor_id,
    )
    offer = get_object_or_404(
        SourcingVendorOffer.objects.for_company(request.company).select_related("material"),
        pk=offer_id,
        vendor=vendor,
    )
    if request.method == "POST":
        form = SourcingVendorOfferForm(request.POST, instance=offer, company=request.company)
        if form.is_valid():
            try:
                update_vendor_offer(
                    actor_membership=_membership(request),
                    vendor_id=vendor.pk,
                    offer_id=offer.pk,
                    cleaned_data={key: value for key, value in form.cleaned_data.items() if key not in {"verified_now", "contact_name"}},
                    verified_now=bool(form.cleaned_data.get("verified_now")),
                    contact_name=str(form.cleaned_data.get("contact_name") or ""),
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Supply Catalog item was updated.")
                return redirect(f"{reverse('sourcing:vendor_detail', args=[vendor.pk])}#catalog")
    else:
        form = SourcingVendorOfferForm(instance=offer, company=request.company)
    context = _base_context(
        request,
        page_key="sourcing-vendors",
        page_title="Edit Supply Item",
        page_subtitle=f"{vendor.display_name or vendor.name} · {offer.material.name}",
    )
    context.update(form=form, vendor=vendor, offer=offer, submit_label="Save Supply Item")
    return render(request, "sourcing/vendors/offer_form.html", context, status=400 if request.method == "POST" and form.errors else 200)


@login_required
def vendor_offer_status(request: HttpRequest, vendor_id, offer_id) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Supply Catalog status changes require POST.")
    is_active = str(request.POST.get("active") or "").lower() in {"1", "true", "yes", "active"}
    try:
        set_vendor_offer_active(
            actor_membership=_membership(request),
            vendor_id=vendor_id,
            offer_id=offer_id,
            is_active=is_active,
            request=request,
        )
    except (ValidationError, SourcingVendor.DoesNotExist, SourcingVendorOffer.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, "Supply Catalog item status was updated.")
    return redirect(f"{reverse('sourcing:vendor_detail', args=[vendor_id])}#catalog")


@login_required
def data_exchange(request: HttpRequest) -> HttpResponse:
    _require_sourcing(request)
    _require_data_exchange(request)
    membership = _membership(request)
    import_choices = tuple((key, label) for key, label in IMPORT_DATASETS if _can_import_dataset(membership, key))
    export_choices = tuple((key, label) for key, label in EXPORT_DATASETS if _can_export_dataset(membership, key))
    result = None
    if request.method == "POST":
        form = SourcingImportUploadForm(request.POST, request.FILES, dataset_choices=import_choices)
        if form.is_valid():
            dataset = form.cleaned_data["dataset"]
            if not _can_import_dataset(membership, dataset):
                raise PermissionDenied("Edit access for this Sourcing dataset is required.")
            try:
                headers, records = read_import_rows(form.cleaned_data["file"])
                result = import_sourcing_rows(
                    actor_membership=membership,
                    dataset=dataset,
                    headers=headers,
                    records=records,
                    dry_run=bool(form.cleaned_data.get("dry_run")),
                    request=request,
                )
                if result.errors:
                    messages.error(request, f"Import was not applied: {len(result.errors)} row(s) need correction.")
                elif result.dry_run:
                    messages.success(request, f"Validation passed for {result.total} row(s). No data was changed.")
                else:
                    messages.success(request, f"Imported {result.total} row(s): {result.creates} created, {result.updates} updated.")
            except ValidationError as exc:
                form.add_error("file", "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        form = SourcingImportUploadForm(dataset_choices=import_choices)
    context = _base_context(
        request,
        page_key="sourcing-data-exchange",
        page_title="Sourcing Data Exchange",
        page_subtitle="Controlled CSV/XLSX import, filtered export and bulk reference maintenance.",
    )
    context.update({
        "form": form,
        "import_result": result,
        "import_choices": import_choices,
        "export_choices": export_choices,
        "max_import_rows": 5000,
    })
    return render(request, "sourcing/data_exchange.html", context)


@login_required
def data_export(request: HttpRequest, dataset: str) -> HttpResponse:
    _require_sourcing(request)
    membership = _membership(request)
    if not _can_export_dataset(membership, dataset):
        raise PermissionDenied("Sourcing export plus dataset view access is required.")
    try:
        payload, filename, content_type, _row_count = build_export(
            actor_membership=membership,
            dataset=dataset,
            fmt=request.GET.get("format", "xlsx"),
            params=request.GET,
            request=request,
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("sourcing:data_exchange")
    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
