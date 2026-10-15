from __future__ import annotations

from decimal import Decimal
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.utils import timezone
from django.http import FileResponse, JsonResponse
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from django.db import IntegrityError
from django.db.transaction import atomic
from uuid import UUID
from .models.base import clean_text, normalize_text
from .freshness import sourcing_freshness_policy

from .access import (
    membership_can_manage_sourcing_masters,
    membership_can_manage_manpower_sourcing,
    membership_can_manage_vendor_sourcing,
    membership_can_export_sourcing,
    membership_can_view_sourcing_masters,
    membership_can_view_manpower_sourcing,
    membership_can_view_vendor_sourcing,
    membership_can_view_subcontractor_sourcing,
    membership_can_manage_subcontractor_sourcing,
    membership_has_any_sourcing_access,
    sourcing_access_context,
)
from .onboarding_forms import SourcingManpowerOnboardingFormSet, SourcingSubcontractorOnboardingFormSet
from .onboarding_categories import pending_master_categories
from .forms import (
    SourcingMaterialForm,
    SourcingServiceForm,
    SourcingManpowerSupplierForm,
    SourcingManpowerContactForm,
    SourcingVendorNewMaterialFormSet,
    SourcingVendorOnboardingOfferFormSet,
    SourcingTradeForm,
    SourcingWorkforceOfferForm,
    SourcingWorkforceOfferVerificationForm,
    SourcingVendorContactForm,
    SourcingVendorForm,
    SourcingVendorOfferForm,
    SourcingVendorOfferVerificationForm,
    SourcingSubcontractorForm, SourcingSubcontractorDocumentForm,
    SourcingSubcontractorContactForm, SourcingSubcontractorVerificationForm,
    SourcingSubcontractorServiceForm, SourcingSubcontractorServiceVerifyForm,
    SourcingImportUploadForm,
    sourcing_material_categories,
)
from .exchange import (
    EXPORT_DATASETS,
    IMPORT_DATASETS,
    build_export,
    build_import_template,
    import_sourcing_rows,
    read_import_rows,
)
from .models import (
    SourcingAvailability,
    SourcingRateBasis,
    SourcingEntityStatus,
    SourcingMaterial,
    SourcingService,
    SourcingManpowerSupplier,
    SourcingManpowerContact,
    SourcingTrade,
    SourcingWorkforceOffer,
    SourcingVendor,
    SourcingVendorContact,
    SourcingVendorOffer,
    SourcingSubcontractor,
    SourcingSubcontractorContact, SourcingSubcontractorService, SourcingServiceRateBasis,
    SourcingSubcontractorDocument, SubcontractorQualificationReview,
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
from .selectors.services_master import (
    PAGE_SIZES as SERVICE_PAGE_SIZES, service_categories, service_directory_page,
)
from .services.services_master import (
    create_service, update_service, set_service_active, delete_service, suggest_service_code,
)
from .selectors.manpower import PAGE_SIZES as MANPOWER_PAGE_SIZES, manpower_directory_page, manpower_history
from .selectors.trades import PAGE_SIZES as TRADE_PAGE_SIZES, trade_directory_page
from .selectors.workforce import (
    OVERVIEW_PREVIEW_LIMIT as WORKFORCE_OVERVIEW_PREVIEW_LIMIT,
    PAGE_SIZES as WORKFORCE_CATALOG_PAGE_SIZES,
    workforce_catalog_overview,
    workforce_catalog_page,
)
from .selectors.service_finder import (
    PAGE_SIZES as SERVICE_FINDER_PAGE_SIZES, service_finder_categories, service_finder_page,
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
from .selectors.unified import capability_queryset, parse_filters
from .selectors.subcontractor_catalog import (
    catalog_page as subcontractor_catalog_page,
    catalog_history_page as subcontractor_catalog_history_page,
    PAGE_SIZES as SUBCONTRACTOR_CATALOG_PAGE_SIZES,
    HISTORY_PAGE_SIZES as SUBCONTRACTOR_HISTORY_PAGE_SIZES,
)
from .services.subcontractor_catalog import (
    create_service_offer, update_service_offer, verify_service_offer,
    set_service_offer_active, delete_service_offer,
)
from .selectors.subcontractors import (
    PAGE_SIZES as SUBCONTRACTOR_PAGE_SIZES, subcontractor_directory_page, subcontractor_history,
    subcontractor_verification_page, stamp_subcontractor_freshness,
)
from .services.subcontractor_verification import verify_subcontractor
from .services.subcontractor_documents import (
    create_document, update_document, review_document, delete_document,
)
from .services.subcontractors import (
    suggest_subcontractor_code, create_subcontractor, update_subcontractor,
    set_subcontractor_status, archive_subcontractor, restore_subcontractor_archive,
    trash_subcontractor, restore_subcontractor_trash, delete_subcontractor,
    create_subcontractor_contact, update_subcontractor_contact,
    deactivate_subcontractor_contact, delete_subcontractor_contact,
)
from .services.catalog import (
    create_material,
    create_vendor_offer,
    delete_material,
    delete_vendor_offer,
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
    delete_manpower_supplier,
    deactivate_manpower_contact,
    delete_manpower_contact,
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
    delete_trade,
    delete_workforce_offer,
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
    create_vendor_with_materials,
    create_vendor_contact,
    delete_vendor,
    deactivate_vendor_contact,
    delete_vendor_contact,
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


def _require_subcontractor_view(request: HttpRequest) -> None:
    if not membership_can_view_subcontractor_sourcing(_membership(request)):
        raise PermissionDenied("Subcontractor Sourcing view authority is required.")


def _require_subcontractor_manage(request: HttpRequest) -> None:
    if not membership_can_manage_subcontractor_sourcing(_membership(request)):
        raise PermissionDenied("Subcontractor Sourcing edit authority is required.")


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
        or membership_can_manage_subcontractor_sourcing(membership)
        or membership_can_manage_sourcing_masters(membership)
    ):
        raise PermissionDenied("Sourcing data-exchange access is required.")


def _can_import_dataset(membership, dataset: str) -> bool:
    if dataset in {"vendors", "vendor_catalog"}:
        return membership_can_manage_vendor_sourcing(membership)
    if dataset in {"manpower_suppliers", "workforce_catalog"}:
        return membership_can_manage_manpower_sourcing(membership)
    if dataset == "subcontractors" or dataset == "subcontractor_service_catalog":
        return membership_can_manage_subcontractor_sourcing(membership)
    if dataset in {"materials", "trades", "services"}:
        return membership_can_manage_sourcing_masters(membership)
    return False


def _can_export_dataset(membership, dataset: str) -> bool:
    if not membership_can_export_sourcing(membership):
        return False
    if dataset in {"vendors", "vendor_catalog"}:
        return membership_can_view_vendor_sourcing(membership)
    if dataset in {"manpower_suppliers", "workforce_catalog"}:
        return membership_can_view_manpower_sourcing(membership)
    if dataset in {"subcontractors", "subcontractor_service_catalog"}:
        return membership_can_view_subcontractor_sourcing(membership)
    if dataset in {"materials", "trades", "services"}:
        return membership_can_view_sourcing_masters(membership)
    return False


def _base_context(request: HttpRequest, *, page_key: str, page_title: str, page_subtitle: str = "") -> dict[str, object]:
    return {
        "page_key": page_key,
        "page_title": page_title,
        "page_subtitle": page_subtitle,
        "SOURCING_ACCESS": sourcing_access_context(_membership(request)),
        "can_create_master": membership_can_manage_sourcing_masters(_membership(request)),
    }




# Upgrade: searchable, company-scoped reference selection and inline master creation.
# This API does not mutate Inventory, Payroll or contracting records.
_LOOKUP_CATALOGS = {
    "material": (SourcingMaterial, SourcingVendorOffer, "material"),
    "trade": (SourcingTrade, SourcingWorkforceOffer, "trade"),
    "service": (SourcingService, SourcingSubcontractorService, "service"),
}


def _lookup_authorized(request, kind):
    member = _membership(request)
    checks = {
        "material": membership_can_manage_vendor_sourcing,
        "trade": membership_can_manage_manpower_sourcing,
        "service": membership_can_manage_subcontractor_sourcing,
    }
    return bool(member and (checks[kind](member) or membership_can_view_sourcing_masters(member)))


def _lookup_result(obj):
    return {"id": str(obj.pk), "name": obj.name, "code": obj.code,
            "category": obj.category, "label": f"{obj.name} · {obj.code}"}


@login_required
@require_http_methods(["GET", "POST"])
def reference_lookup(request: HttpRequest, kind: str) -> HttpResponse:
    """Fast capped suggestions; creation remains permission-gated and audited."""
    if kind not in _LOOKUP_CATALOGS:
        raise Http404("Unknown sourcing master.")
    model, offer_model, foreign_key = _LOOKUP_CATALOGS[kind]
    if request.method == "GET":
        if request.GET.get("form") == "1":
            # Render the SAME ModelForm fields used by the standalone master page.
            # A separate prefix prevents collisions with the unsaved capability form.
            _require_master_manage(request)
            initial_codes = {
                "material": suggest_material_code,
                "trade": suggest_trade_code,
                "service": suggest_service_code,
            }
            fields = {"material": SourcingMaterialForm, "trade": SourcingTradeForm,
                      "service": SourcingServiceForm}
            kwargs = {"prefix": "master", "initial": {"code": initial_codes[kind]()}}
            if kind != "trade":
                kwargs["company"] = request.company
            form = fields[kind](**kwargs)
            return render(request, f"sourcing/reference_master_fields/{kind}.html", {"form": form})
        if not _lookup_authorized(request, kind):
            raise PermissionDenied("Sourcing catalog access required.")
        queryset = model.objects.for_company(request.company).filter(is_active=True)
        selected_id = request.GET.get("selected", "").strip()
        if selected_id:
            try:
                chosen = model.objects.for_company(request.company).filter(pk=UUID(selected_id)).first()
            except (ValueError, TypeError, AttributeError):
                chosen = None
            return JsonResponse({"results": [_lookup_result(chosen)] if chosen else []})
        raw_query = clean_text(request.GET.get("q", ""))[:80]
        if not raw_query:
            # Aggregate by the indexed offer FK, not over every master row.
            # Busy/reference items appear first; alphabetical active items fill gaps.
            counts = (offer_model.objects.for_company(request.company).filter(
                is_active=True, **{f"{foreign_key}__is_active": True,
                                  f"{foreign_key}__company": request.company})
                .order_by().values(f"{foreign_key}_id").annotate(usage=Count("pk"))
                .order_by("-usage", f"{foreign_key}_id")[:12])
            popular_ids = [entry[f"{foreign_key}_id"] for entry in counts]
            keyed = queryset.in_bulk(popular_ids)
            results = [keyed[pk] for pk in popular_ids if pk in keyed]
            if len(results) < 12:
                results += list(queryset.exclude(pk__in=popular_ids)
                                .order_by("normalized_name", "pk")[:12 - len(results)])
        else:
            # Prioritize exact/prefix matches, but keep subsequent pages available
            # for larger catalogs. Querysets are sliced in SQL (not materialized).
            term = normalize_text(raw_query)
            try:
                page = max(1, min(int(request.GET.get("page", "1")), 50))
            except (ValueError, TypeError):
                page = 1
            matches = (queryset.filter(
                Q(normalized_name__startswith=term) | Q(code__istartswith=raw_query)
                | Q(normalized_name__icontains=term) | Q(category__icontains=raw_query)
                | Q(normalized_aliases__icontains=term)
            ).annotate(
                relevance=Case(
                    When(normalized_name=term, then=Value(0)),
                    When(normalized_name__startswith=term, then=Value(1)),
                    When(code__istartswith=raw_query, then=Value(2)),
                    default=Value(3), output_field=IntegerField(),
                )
            ).order_by("relevance", "normalized_name", "pk"))
            offset = (page - 1) * 12
            window = list(matches[offset:offset + 13])
            results = window[:12]
            return JsonResponse({"results": [_lookup_result(entry) for entry in results],
                                 "has_more": len(window) > 12, "page": page})
        return JsonResponse({"results": [_lookup_result(entry) for entry in results],
                             "has_more": False, "page": 1})

    # A user permitted to edit a supplier is NOT automatically permitted to
    # create company-wide master vocabulary. Match the standalone access check.
    _require_master_manage(request)
    declared_size = request.META.get("CONTENT_LENGTH", "")
    if declared_size.isdecimal() and int(declared_size) > 16384:
        return JsonResponse({"error": "Reference details are too large."}, status=413)

    # The new modal uses `master-` prefixed fields, while old cached JavaScript
    # can still submit the previous unprefixed payload during rolling deploys.
    prefix = "master" if any(key.startswith("master-") for key in request.POST) else None
    posted = request.POST.copy()
    def key_for(field):
        return f"{prefix}-{field}" if prefix else field
    posted[key_for("name")] = clean_text(posted.get(key_for("name")))
    if not posted[key_for("name")]:
        return JsonResponse({"errors": {"name": ["Enter a reference name."]}}, status=400)
    forms = {"material": SourcingMaterialForm, "trade": SourcingTradeForm,
             "service": SourcingServiceForm}
    suggest_code = {"material": suggest_material_code,
                    "trade": suggest_trade_code,
                    "service": suggest_service_code}
    posted[key_for("code")] = posted.get(key_for("code")) or suggest_code[kind]()
    kwargs = {"prefix": prefix}
    if kind != "trade":
        kwargs["company"] = request.company
        # Preserve compatibility with old inline dialogs that submitted a free
        # text category instead of the standalone form's controlled choice.
        if prefix is None:
            category = clean_text(posted.get("category"))
            if category:
                existing_categories = (sourcing_material_categories(request.company) if kind == "material"
                                       else service_categories(request.company))
                existing = next((value for value in existing_categories
                                 if normalize_text(value) == normalize_text(category)), None)
                if existing:
                    posted["category"] = existing
                else:
                    posted["category"] = "__new__"
                    posted["new_category"] = category
    form = forms[kind](posted, **kwargs)
    create_fn = {"material": create_material, "trade": create_trade, "service": create_service}[kind]
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    cleaned = {key: val for key, val in form.cleaned_data.items() if key != "new_category"}
    try:
        # Each service creates the master and records the standard sourcing audit.
        created = create_fn(actor_membership=_membership(request), cleaned_data=cleaned, request=request)
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, "message_dict") else {"__all__": exc.messages}
        return JsonResponse({"errors": errors}, status=400)
    except IntegrityError:
        # Concurrent duplicate insert (unique company + normalized name/code).
        return JsonResponse({"errors": {"name": ["This reference already exists. Search and select it."]}}, status=409)
    return JsonResponse({"item": _lookup_result(created)}, status=201)


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
            page_subtitle="Reference-only vendor, manpower and subcontractor sourcing.",
        ),
    )


def _integrated_offer_querystring(finder, kind: str) -> str:
    """Canonical, bounded filters for stable pagination and copyable view links."""
    fields = ["query", "availability", "freshness", "category", "location", "rate_min",
              "rate_max", "sort", "direction", "page_size"]
    fields.append({"vendor": "vendor", "workforce": "supplier", "service": "subcontractor"}[kind])
    if kind in {"workforce", "service"}:
        fields.append("rate_basis")
    if kind == "service":
        fields.append("currency")
    names = {"query": "q", "direction": "dir"}
    return urlencode([("view", "offers"), *[(names.get(key, key), getattr(finder, key)) for key in fields]])


def _render_integrated_offers(request: HttpRequest, *, kind: str) -> HttpResponse:
    """Search catalog records on their parent directory, without a second page or N+1 lists."""
    config = {
        "vendor": (material_finder_page, material_finder_categories, "sourcing/vendors/list.html",
                   "sourcing-vendors", "Vendors", "vendor", membership_can_manage_vendor_sourcing),
        "workforce": (workforce_finder_page, workforce_finder_categories, "sourcing/manpower/list.html",
                      "sourcing-manpower", "Manpower Suppliers", "supplier", membership_can_manage_manpower_sourcing),
        "service": (service_finder_page, service_finder_categories, "sourcing/subcontractors/list.html",
                    "sourcing-subcontractors", "Subcontractors", "subcontractor", membership_can_manage_subcontractor_sourcing),
    }
    selector, categories, template, page_key, title, _field, permission = config[kind]
    finder = selector(company=request.company, params=request.GET)
    context = _base_context(
        request, page_key=page_key, page_title=title,
        page_subtitle="Search and compare sourcing-only company capabilities and their verification freshness.",
    )
    context.update(
        view_mode="offers", finder=finder, page_obj=finder.page_obj,
        offers=finder.page_obj.object_list, page_sizes=(25, 50, 100),
        availability_choices=SourcingAvailability.choices,
        categories=categories(company=request.company),
        filter_querystring=_integrated_offer_querystring(finder, kind),
        can_manage=permission(_membership(request)),
    )
    if kind == "service":
        context["rate_basis_choices"] = SourcingServiceRateBasis.choices
    return render(request, template, context)


def _legacy_directory_query(request):
    """Old view=offers links are safe permanent bookmark inputs, not a second UI."""
    if request.GET.get('view') != 'offers':
        return None
    params = request.GET.copy()
    params.pop('view', None)
    for old_key in ('vendor', 'supplier', 'subcontractor'):
        if params.get(old_key) and not params.get('q'):
            params['q'] = params[old_key]
        params.pop(old_key, None)
    # The old offer-level sorting fields do not apply to provider rows.
    if params.get('sort') not in {'name', 'code', 'city', 'updated', 'verified'}:
        params.pop('sort', None)
    return redirect(f"{request.path}?{params.urlencode()}" if params else request.path)


def _capability_fragment(request, *, kind):
    """Paginated on-demand detail for one company; no global offer-prefetch."""
    from uuid import UUID
    from .selectors.unified import KINDS
    provider_models = {
        'vendor': SourcingVendor,
        'manpower': SourcingManpowerSupplier,
        'subcontractor': SourcingSubcontractor,
    }
    try:
        provider_id = UUID(request.GET.get('provider', ''))
    except (TypeError, AttributeError, ValueError):
        raise Http404('Invalid provider')
    provider = get_object_or_404(provider_models[kind].objects.for_company(request.company), pk=provider_id)
    filters = parse_filters(kind=kind, params=request.GET)
    text = str(request.GET.get('q') or '').strip()[:160]
    # A company-name search should display its offers rather than an empty tray.
    provider_text = f"{provider.name} {provider.code} {getattr(provider, 'display_name', '')}".casefold()
    if text and text.casefold() in provider_text:
        text = ''
    qs = capability_queryset(company=request.company, kind=kind, filters=filters,
                             provider_id=provider.pk, query=text)
    master_fk = {'vendor': 'material', 'manpower': 'trade', 'subcontractor': 'service'}[kind]
    qs = qs.select_related(master_fk).order_by(f'{master_fk}__normalized_name', 'pk')
    try:
        page_num = max(1, int(str(request.GET.get('cap_page') or '1')))
    except (ValueError, TypeError):
        page_num = 1
    page = Paginator(qs, 20).get_page(page_num)
    return render(request, 'sourcing/unified/capabilities.html', {
        'offers': page.object_list, 'offer_page': page, 'kind': kind,
        'provider': provider, 'can_manage': {
            'vendor': membership_can_manage_vendor_sourcing,
            'manpower': membership_can_manage_manpower_sourcing,
            'subcontractor': membership_can_manage_subcontractor_sourcing,
        }[kind](_membership(request)),
    })


def _unified_context(request, *, kind):
    from .selectors.material_finder import material_finder_categories
    from .selectors.workforce_finder import workforce_finder_categories
    from .selectors.service_finder import service_finder_categories
    filters = parse_filters(kind=kind, params=request.GET)
    categories = {
        'vendor': material_finder_categories,
        'manpower': workforce_finder_categories,
        'subcontractor': service_finder_categories,
    }[kind](company=request.company)
    return {
        'capability_filters': filters,
        'capability_categories': categories,
        'availability_choices': SourcingAvailability.choices,
        'freshness_policy': sourcing_freshness_policy(company=request.company),
        'kind': kind,
        'rate_basis_choices': (SourcingRateBasis.choices if kind == 'manpower'
                               else SourcingServiceRateBasis.choices if kind == 'subcontractor' else ()),
    }


@login_required
def vendor_list(request: HttpRequest) -> HttpResponse:
    _require_vendor_view(request)
    old_url = _legacy_directory_query(request)
    if old_url is not None:
        return old_url
    if request.GET.get('fragment') == 'capabilities':
        return _capability_fragment(request, kind='vendor')
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
    vendors = list(directory.page_obj.object_list)
    context.update(_unified_context(request, kind='vendor'))
    context.update(
        directory=directory,
        page_obj=directory.page_obj,
        vendors=vendors,
        counts=counts,
        page_sizes=PAGE_SIZES,
        can_manage=membership_can_manage_vendor_sourcing(_membership(request)),
    )
    return render(request, "sourcing/vendors/list.html", context)


@login_required
def vendor_create(request: HttpRequest) -> HttpResponse:
    _require_vendor_manage(request)
    membership = _membership(request)
    can_create_materials = membership_can_manage_sourcing_masters(membership)
    category_values = sourcing_material_categories(request.company)
    if request.method == "POST" and can_create_materials:
        category_values = list(dict.fromkeys([
            *category_values,
            *pending_master_categories(
                request.POST, category_field="new_material_category",
                new_category_field="new_material_new_category",
                name_field="new_material_name",
            ),
        ]))
    formset_kwargs = {
        "prefix": "new_materials",
        "form_kwargs": {"company": request.company, "categories": category_values},
    }
    offers_kwargs = {
        "prefix": "supply_items",
        "form_kwargs": {
            "company": request.company,
            "can_create_materials": can_create_materials,
            "categories": category_values,
        },
    }
    offer_formset = (
        SourcingVendorOnboardingOfferFormSet(request.POST, **offers_kwargs)
        if request.method == "POST" and "supply_items-TOTAL_FORMS" in request.POST
        else SourcingVendorOnboardingOfferFormSet(**offers_kwargs)
    )
    if request.method == "POST":
        form = SourcingVendorForm(request.POST, company=request.company, include_materials=True)
        if "supply_items-TOTAL_FORMS" not in request.POST and any(
            key.startswith("supply_items-") for key in request.POST
        ):
            form.add_error(None, "The supply-item editor data was incomplete. Reopen the form and try again.")
        inline_formset_submitted = "new_materials-TOTAL_FORMS" in request.POST
        new_material_formset = None
        if can_create_materials:
            new_material_formset = (
                SourcingVendorNewMaterialFormSet(request.POST, **formset_kwargs)
                if inline_formset_submitted
                else SourcingVendorNewMaterialFormSet(**formset_kwargs)
            )
        if not can_create_materials:
            inline_material_requested = any(
                key.startswith("new_materials-")
                and key.rsplit("-", 1)[-1] in {"name", "code", "category", "new_category", "default_unit"}
                and str(value or "").strip()
                for key, value in request.POST.items()
            )
            if inline_material_requested:
                form.add_error(None, "Sourcing Reference Masters edit authority is required to create new materials.")

        form_valid = form.is_valid()
        formset_valid = (
            new_material_formset.is_valid()
            if new_material_formset is not None and inline_formset_submitted
            else True
        )
        offers_valid = (
            offer_formset.is_valid()
            if "supply_items-TOTAL_FORMS" in request.POST
            else True  # Pre-upgrade forms remain supported during rolling deployments.
        )
        if form_valid and formset_valid and offers_valid:
            cleaned_data = {key: value for key, value in form.cleaned_data.items() if key != "materials"}
            materials = list(form.cleaned_data.get("materials") or ())
            new_materials = []
            if new_material_formset is not None and inline_formset_submitted:
                new_materials = [
                    material_form.material_data()
                    for material_form in new_material_formset.forms
                    if material_form.cleaned_data
                    and not material_form.cleaned_data.get("DELETE")
                    and material_form.cleaned_data.get("name")
                ]
            complete_offers = []
            for offer_form in offer_formset.forms:
                if not offer_form.cleaned_data or offer_form.cleaned_data.get("DELETE"):
                    continue
                complete_offers.append({
                    **offer_form.offer_data(),
                    "material": offer_form.cleaned_data.get("material"),
                    "draft_material": offer_form.cleaned_data.get("draft_material"),
                    "verified_now": offer_form.cleaned_data.get("verified_now", False),
                    "contact_name": offer_form.cleaned_data.get("contact_name", ""),
                })
            try:
                vendor = create_vendor_with_materials(
                    actor_membership=membership,
                    cleaned_data=cleaned_data,
                    materials=materials,
                    new_materials=new_materials,
                    offers=complete_offers,
                    auto_code=not str(request.POST.get("code") or "").strip(),
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                linked_material_count = len(materials) + len(new_materials) + len(complete_offers)
                if linked_material_count:
                    new_material_detail = ""
                    new_master_count = len(new_materials) + sum(
                        1 for offer in complete_offers if offer.get("draft_material")
                    )
                    if new_master_count:
                        new_material_detail = (
                            f", including {new_master_count} new material master "
                            f"record{'s' if new_master_count != 1 else ''}"
                        )
                    messages.success(
                        request,
                        f"Vendor {vendor.display_name or vendor.name} was created with {linked_material_count} material "
                        f"type{'s' if linked_material_count != 1 else ''}{new_material_detail}.",
                    )
                else:
                    messages.success(request, f"Vendor {vendor.display_name or vendor.name} was created.")
                return redirect("sourcing:vendor_detail", vendor_id=vendor.pk)
    else:
        form = SourcingVendorForm(
            company=request.company,
            include_materials=True,
        )
        new_material_formset = SourcingVendorNewMaterialFormSet(**formset_kwargs) if can_create_materials else None
    context = _base_context(
        request,
        page_key="sourcing-vendors",
        page_title="New Vendor",
        page_subtitle="Add a reference-only sourcing Vendor. Nothing here creates purchasing, stock or accounting activity.",
    )
    context.update(
        form=form,
        submit_label="Create Vendor",
        cancel_url="sourcing:vendor_list",
        show_materials=True,
        can_create_materials=can_create_materials,
        new_material_formset=new_material_formset,
        offer_formset=offer_formset,
        can_create_master=False,  # Draft new masters are committed with the Vendor.
    )
    has_form_errors = (
        bool(form.errors)
        or bool(new_material_formset and new_material_formset.errors)
        or bool(offer_formset.errors)
        or bool(offer_formset.non_form_errors())
    )
    return render(
        request,
        "sourcing/vendors/form.html",
        context,
        status=400 if request.method == "POST" and has_form_errors else 200,
    )


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
        form = SourcingVendorForm(request.POST, instance=vendor, company=request.company)
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
        form = SourcingVendorForm(instance=vendor, company=request.company)
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
def vendor_delete(request: HttpRequest, vendor_id) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Vendor permanent deletion requires POST.")
    try:
        result = delete_vendor(
            actor_membership=_membership(request),
            vendor_id=vendor_id,
            confirmation=request.POST.get("confirmation", ""),
            reason=request.POST.get("reason", ""),
            request=request,
        )
    except (ValidationError, SourcingVendor.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        if SourcingVendor.objects.for_company(request.company).filter(pk=vendor_id).exists():
            return redirect("sourcing:vendor_detail", vendor_id=vendor_id)
        return redirect("sourcing:vendor_list")
    messages.success(
        request,
        f"{result['label']} was permanently deleted with {result['offers_deleted']} Supply Catalog row(s) and {result['contacts_deleted']} contact(s).",
    )
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
def vendor_contact_delete(request: HttpRequest, vendor_id, contact_id) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Vendor contact permanent deletion requires POST.")
    try:
        result = delete_vendor_contact(
            actor_membership=_membership(request),
            vendor_id=vendor_id,
            contact_id=contact_id,
            request=request,
        )
    except (ValidationError, SourcingVendor.DoesNotExist, SourcingVendorContact.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, f"{result['label']} was permanently deleted from Vendor contacts.")
    return redirect("sourcing:vendor_detail", vendor_id=vendor_id)


@login_required
def manpower_supplier_list(request: HttpRequest) -> HttpResponse:
    _require_manpower_view(request)
    old_url = _legacy_directory_query(request)
    if old_url is not None:
        return old_url
    if request.GET.get('fragment') == 'capabilities':
        return _capability_fragment(request, kind='manpower')
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
    context.update(_unified_context(request, kind='manpower'))
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
    membership = _membership(request)
    allow_masters = membership_can_manage_sourcing_masters(membership)
    bound = request.method == "POST" and "supply_items-TOTAL_FORMS" in request.POST
    offers = SourcingManpowerOnboardingFormSet(
        request.POST if bound else None,
        prefix="supply_items",
        form_kwargs={"company": request.company, "can_create_master": allow_masters},
    )
    form = SourcingManpowerSupplierForm(request.POST if request.method == "POST" else None,
                                       company=request.company)
    if request.method == "POST":
        if not bound and any(key.startswith("supply_items-") for key in request.POST):
            form.add_error(None, "Incomplete workforce editor submission. Reload the form.")
        form_ok = form.is_valid()
        offers_ok = offers.is_valid() if bound else True
        if form_ok and offers_ok and not form.non_field_errors():
            try:
                with atomic():
                    supplier = create_manpower_supplier(
                        actor_membership=membership, cleaned_data=form.cleaned_data, request=request)
                    for offer_form in offers.forms:
                        data = offer_form.cleaned_data
                        if not data or data.get("DELETE"):
                            continue
                        trade = data.get("trade")
                        if data.get("draft_master"):
                            if not allow_masters:
                                raise ValidationError("Reference Masters edit permission required.")
                            trade = create_trade(actor_membership=membership,
                                                 cleaned_data=data["draft_master"], request=request)
                        create_workforce_offer(
                            actor_membership=membership, supplier_id=supplier.pk,
                            cleaned_data={**offer_form.offer_data(), "trade": trade},
                            verified_now=data.get("verified_now", False),
                            contact_name=data.get("contact_name", ""), request=request,
                        )
            except (ValidationError, IntegrityError) as exc:
                _apply_validation_error(form, exc if isinstance(exc, ValidationError)
                                        else ValidationError("Unable to save provider and capabilities. Check for duplicate records."))
            else:
                messages.success(request, f"Manpower Supplier {supplier.name} created with workforce capabilities.")
                return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier.pk)
    context = _base_context(
        request, page_key="sourcing-manpower", page_title="New Manpower Supplier",
        page_subtitle="Reference-only manpower source.",
    )
    context.update(form=form, offer_formset=offers, can_create_master=allow_masters,
                   show_capabilities=True, submit_label="Create Manpower Supplier")
    return render(request, "sourcing/manpower/form.html", context,
                  status=400 if request.method == "POST" and (form.errors or offers.errors) else 200)


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
def manpower_supplier_delete(request: HttpRequest, supplier_id) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Manpower Supplier permanent deletion requires POST.")
    try:
        result = delete_manpower_supplier(
            actor_membership=_membership(request),
            supplier_id=supplier_id,
            confirmation=request.POST.get("confirmation", ""),
            reason=request.POST.get("reason", ""),
            request=request,
        )
    except (ValidationError, SourcingManpowerSupplier.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        if SourcingManpowerSupplier.objects.for_company(request.company).filter(pk=supplier_id).exists():
            return redirect("sourcing:manpower_supplier_detail", supplier_id=supplier_id)
        return redirect("sourcing:manpower_supplier_list")
    messages.success(
        request,
        f"{result['label']} was permanently deleted with {result['offers_deleted']} Workforce row(s) and {result['contacts_deleted']} contact(s).",
    )
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
def manpower_contact_delete(request: HttpRequest, supplier_id, contact_id) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Manpower contact permanent deletion requires POST.")
    try:
        result = delete_manpower_contact(
            actor_membership=_membership(request),
            supplier_id=supplier_id,
            contact_id=contact_id,
            request=request,
        )
    except (ValidationError, SourcingManpowerSupplier.DoesNotExist, SourcingManpowerContact.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, f"{result['label']} was permanently deleted from Manpower Supplier contacts.")
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
def workforce_offer_delete(request: HttpRequest, supplier_id, offer_id) -> HttpResponse:
    _require_manpower_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Workforce Catalog permanent deletion requires POST.")
    try:
        result = delete_workforce_offer(
            actor_membership=_membership(request),
            supplier_id=supplier_id,
            offer_id=offer_id,
            request=request,
        )
    except (ValidationError, SourcingManpowerSupplier.DoesNotExist, SourcingWorkforceOffer.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, f"{result['label']} was permanently deleted from this Supplier's Workforce Catalog.")
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


def _legacy_finder_redirect(request: HttpRequest, *, destination: str) -> HttpResponse:
    """Existing links stay usable while all finder UI lives in the directory."""
    params = request.GET.copy()
    for old_key in ('vendor', 'supplier', 'subcontractor'):
        if params.get(old_key) and not params.get('q'):
            params['q'] = params[old_key]
        params.pop(old_key, None)
    if params.get('sort') not in {'name', 'code', 'city', 'updated', 'verified'}:
        params.pop('sort', None)
    address = reverse(destination)
    return redirect(f"{address}?{params.urlencode()}" if params else address)


@login_required
def material_finder(request: HttpRequest) -> HttpResponse:
    _require_vendor_view(request)
    return _legacy_finder_redirect(request, destination="sourcing:vendor_list")


@login_required
def service_finder(request: HttpRequest) -> HttpResponse:
    _require_subcontractor_view(request)
    return _legacy_finder_redirect(request, destination="sourcing:subcontractor_list")


@login_required
def workforce_finder(request: HttpRequest) -> HttpResponse:
    _require_manpower_view(request)
    return _legacy_finder_redirect(request, destination="sourcing:manpower_supplier_list")


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
    category_values = sourcing_material_categories(request.company)
    if request.method == "POST":
        form = SourcingMaterialForm(request.POST, company=request.company, categories=category_values)
        if form.is_valid():
            material_data = {key: value for key, value in form.cleaned_data.items() if key != "new_category"}
            try:
                material = create_material(
                    actor_membership=_membership(request),
                    cleaned_data=material_data,
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, f"Sourcing Material {material.name} was created.")
                return redirect("sourcing:material_list")
    else:
        form = SourcingMaterialForm(
            initial={"code": suggest_material_code()},
            company=request.company,
            categories=category_values,
        )
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
    category_values = sourcing_material_categories(request.company)
    if request.method == "POST":
        form = SourcingMaterialForm(
            request.POST,
            instance=material,
            company=request.company,
            categories=category_values,
        )
        if form.is_valid():
            material_data = {key: value for key, value in form.cleaned_data.items() if key != "new_category"}
            try:
                material = update_material(
                    actor_membership=_membership(request),
                    material_id=material.pk,
                    cleaned_data=material_data,
                    request=request,
                )
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Sourcing Material was updated.")
                return redirect("sourcing:material_list")
    else:
        form = SourcingMaterialForm(
            instance=material,
            company=request.company,
            categories=category_values,
        )
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
def material_delete(request: HttpRequest, material_id) -> HttpResponse:
    _require_master_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Material permanent deletion requires POST.")
    try:
        result = delete_material(
            actor_membership=_membership(request),
            material_id=material_id,
            confirmation=request.POST.get("confirmation", ""),
            request=request,
        )
    except (ValidationError, SourcingMaterial.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(
            request,
            f"{result['label']} was permanently deleted with {result['offers_deleted']} Vendor catalog row(s).",
        )
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
def trade_delete(request: HttpRequest, trade_id) -> HttpResponse:
    _require_master_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Trade permanent deletion requires POST.")
    try:
        result = delete_trade(
            actor_membership=_membership(request),
            trade_id=trade_id,
            confirmation=request.POST.get("confirmation", ""),
            request=request,
        )
    except (ValidationError, SourcingTrade.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(
            request,
            f"{result['label']} was permanently deleted with {result['offers_deleted']} Workforce row(s).",
        )
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
def vendor_offer_delete(request: HttpRequest, vendor_id, offer_id) -> HttpResponse:
    _require_vendor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Supply Catalog permanent deletion requires POST.")
    try:
        result = delete_vendor_offer(
            actor_membership=_membership(request),
            vendor_id=vendor_id,
            offer_id=offer_id,
            request=request,
        )
    except (ValidationError, SourcingVendor.DoesNotExist, SourcingVendorOffer.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, f"{result['label']} was permanently deleted from this Vendor's Supply Catalog.")
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


@login_required
def data_import_template(request: HttpRequest, dataset: str) -> HttpResponse:
    _require_sourcing(request)
    if not _can_import_dataset(_membership(request), dataset):
        raise PermissionDenied("Sourcing dataset edit access is required to retrieve import templates.")
    if request.method != "GET":
        raise PermissionDenied("Import templates require GET.")
    try:
        payload, filename, content_type = build_import_template(
            dataset=dataset, fmt=request.GET.get("format", "xlsx")
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("sourcing:data_exchange")
    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


# Upgrade 02 — company-scoped Sourcing Services reference master.
@login_required
def service_list(request: HttpRequest) -> HttpResponse:
    _require_master_view(request)
    directory = service_directory_page(company=request.company, params=request.GET)
    base_qs = SourcingService.objects.for_company(request.company)
    context = _base_context(
        request, page_key="sourcing-services", page_title="Sourcing Services",
        page_subtitle="Controlled service types for future subcontractor sourcing. No operational service jobs are created.",
    )
    context.update(
        directory=directory, page_obj=directory.page_obj,
        services=directory.page_obj.object_list, page_sizes=SERVICE_PAGE_SIZES,
        categories=service_categories(request.company),
        counts={
            "active": base_qs.filter(is_active=True).count(),
            "inactive": base_qs.filter(is_active=False).count(),
        },
        can_manage=membership_can_manage_sourcing_masters(_membership(request)),
    )
    return render(request, "sourcing/services/list.html", context)


@login_required
def service_create(request: HttpRequest) -> HttpResponse:
    _require_master_manage(request)
    categories = service_categories(request.company)
    if request.method == "POST":
        form = SourcingServiceForm(request.POST, company=request.company, categories=categories)
        if form.is_valid():
            data = {k: v for k, v in form.cleaned_data.items() if k != "new_category"}
            try:
                service = create_service(actor_membership=_membership(request), cleaned_data=data, request=request)
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, f"Sourcing Service {service.name} was created.")
                return redirect("sourcing:service_list")
    else:
        form = SourcingServiceForm(initial={"code": suggest_service_code()}, company=request.company, categories=categories)
    context = _base_context(request, page_key="sourcing-services", page_title="New Sourcing Service",
                            page_subtitle="Create a controlled service type for Subcontractor sourcing.")
    context.update(form=form, submit_label="Create Service")
    return render(request, "sourcing/services/form.html", context,
                  status=400 if request.method == "POST" and form.errors else 200)


@login_required
def service_edit(request: HttpRequest, service_id) -> HttpResponse:
    _require_master_manage(request)
    service = get_object_or_404(SourcingService.objects.for_company(request.company), pk=service_id)
    categories = service_categories(request.company)
    if request.method == "POST":
        form = SourcingServiceForm(request.POST, instance=service, company=request.company, categories=categories)
        if form.is_valid():
            data = {k: v for k, v in form.cleaned_data.items() if k != "new_category"}
            try:
                update_service(actor_membership=_membership(request), service_id=service.pk,
                               cleaned_data=data, request=request)
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Sourcing Service was updated.")
                return redirect("sourcing:service_list")
    else:
        form = SourcingServiceForm(instance=service, company=request.company, categories=categories)
    context = _base_context(request, page_key="sourcing-services", page_title="Edit Sourcing Service",
                            page_subtitle=f"Update {service.code} · {service.name}.")
    context.update(form=form, service=service, submit_label="Save Service")
    return render(request, "sourcing/services/form.html", context,
                  status=400 if request.method == "POST" and form.errors else 200)


@login_required
def service_status(request: HttpRequest, service_id) -> HttpResponse:
    _require_master_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Service status changes require POST.")
    is_active = str(request.POST.get("active") or "").lower() in {"1", "true", "yes", "active"}
    try:
        service = set_service_active(actor_membership=_membership(request), service_id=service_id,
                                     is_active=is_active, request=request)
    except (ValidationError, SourcingService.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, f"{service.name} is now {'Active' if service.is_active else 'Inactive'}.")
    return redirect("sourcing:service_list")


@login_required
def service_delete(request: HttpRequest, service_id) -> HttpResponse:
    _require_master_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Service permanent deletion requires POST.")
    try:
        result = delete_service(actor_membership=_membership(request), service_id=service_id,
                                confirmation=request.POST.get("confirmation", ""), request=request)
    except (ValidationError, SourcingService.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, f"{result['label']} was permanently deleted.")
    return redirect("sourcing:service_list")


# Upgrade 03 · Subcontractor Directory. All access checks precede ORM lookups.

def _subcontractor_context(request, obj, page_title=None):
    context = _base_context(
        request, page_key="sourcing-subcontractors",
        page_title=page_title or obj.display_name or obj.name,
        page_subtitle=f"{obj.code} · Reference-only subcontractor company",
    )
    stamp_subcontractor_freshness(company=request.company, records=[obj])
    context.update(subcontractor=obj, can_manage=membership_can_manage_subcontractor_sourcing(_membership(request)))
    return context


@login_required
def subcontractor_list(request: HttpRequest) -> HttpResponse:
    _require_subcontractor_view(request)
    old_url = _legacy_directory_query(request)
    if old_url is not None:
        return old_url
    if request.GET.get('fragment') == 'capabilities':
        return _capability_fragment(request, kind='subcontractor')
    directory = subcontractor_directory_page(company=request.company, params=request.GET)
    qs = SourcingSubcontractor.objects.for_company(request.company)
    counts = {
        "active": qs.filter(deleted_at__isnull=True, archived_at__isnull=True, status=SourcingEntityStatus.ACTIVE).count(),
        "inactive": qs.filter(deleted_at__isnull=True, archived_at__isnull=True, status=SourcingEntityStatus.INACTIVE).count(),
        "archived": qs.filter(deleted_at__isnull=True, archived_at__isnull=False).count(),
        "trash": qs.filter(deleted_at__isnull=False).count(),
    }
    context = _base_context(
        request, page_key="sourcing-subcontractors", page_title="Subcontractors",
        page_subtitle="Reference companies SESCCO may call for services. No inventory, purchasing, project or payroll transactions.",
    )
    subcontractors = stamp_subcontractor_freshness(company=request.company, records=list(directory.page_obj.object_list))
    context.update(_unified_context(request, kind='subcontractor'))
    context.update(directory=directory, page_obj=directory.page_obj, subcontractors=subcontractors,
                   counts=counts, page_sizes=SUBCONTRACTOR_PAGE_SIZES,
                   can_manage=membership_can_manage_subcontractor_sourcing(_membership(request)))
    return render(request, "sourcing/subcontractors/list.html", context)


@login_required
def subcontractor_create(request: HttpRequest) -> HttpResponse:
    _require_subcontractor_manage(request)
    membership = _membership(request)
    allow_masters = membership_can_manage_sourcing_masters(membership)
    bound = request.method == "POST" and "supply_items-TOTAL_FORMS" in request.POST
    from .selectors.services_master import service_categories
    category_values = service_categories(request.company)
    if bound and allow_masters:
        category_values = list(dict.fromkeys([
            *category_values,
            *pending_master_categories(
                request.POST, category_field="new_master_category",
                new_category_field="new_master_new_category",
                name_field="new_master_name",
            ),
        ]))
    offers = SourcingSubcontractorOnboardingFormSet(
        request.POST if bound else None,
        prefix="supply_items",
        form_kwargs={"company": request.company, "can_create_master": allow_masters,
                     "categories": category_values},
    )
    form = SourcingSubcontractorForm(request.POST if request.method == "POST" else None,
                                    company=request.company)
    if request.method == "POST":
        if not bound and any(key.startswith("supply_items-") for key in request.POST):
            form.add_error(None, "Incomplete service editor submission. Reload the form.")
        form_ok = form.is_valid()
        offers_ok = offers.is_valid() if bound else True
        if form_ok and offers_ok and not form.non_field_errors():
            try:
                with atomic():
                    obj = create_subcontractor(actor_membership=membership,
                                               cleaned_data=form.cleaned_data, request=request)
                    for offer_form in offers.forms:
                        data = offer_form.cleaned_data
                        if not data or data.get("DELETE"):
                            continue
                        service = data.get("service")
                        if data.get("draft_master"):
                            if not allow_masters:
                                raise ValidationError("Reference Masters edit permission required.")
                            service = create_service(actor_membership=membership,
                                                     cleaned_data=data["draft_master"], request=request)
                        create_service_offer(
                            actor_membership=membership, subcontractor_id=obj.pk,
                            cleaned_data={**offer_form.offer_data(), "service": service},
                            verified_now=data.get("verified_now", False),
                            contact_name=data.get("contact_name", ""), request=request,
                        )
            except (ValidationError, IntegrityError) as exc:
                _apply_validation_error(form, exc if isinstance(exc, ValidationError)
                                        else ValidationError("Unable to save provider and capabilities. Check for duplicate records."))
            else:
                messages.success(request, "Subcontractor created with service capabilities.")
                return redirect("sourcing:subcontractor_detail", subcontractor_id=obj.pk)
    context = _base_context(request, page_key="sourcing-subcontractors", page_title="New Subcontractor",
                            page_subtitle="Independent reference-only service provider.")
    context.update(form=form, offer_formset=offers, can_create_master=allow_masters,
                   show_capabilities=True, submit_label="Create Subcontractor")
    return render(request, "sourcing/subcontractors/form.html", context,
                  status=400 if request.method == "POST" and (form.errors or offers.errors) else 200)


@login_required
def subcontractor_detail(request: HttpRequest, subcontractor_id) -> HttpResponse:
    _require_subcontractor_view(request)
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    context = _subcontractor_context(request, obj)
    contacts = list(SourcingSubcontractorContact.objects.for_company(request.company).filter(subcontractor=obj).order_by("-is_active", "-is_primary", "first_name"))
    from .freshness import sourcing_freshness_policy, freshness_key, freshness_label
    policy = sourcing_freshness_policy(company=request.company)
    catalog = subcontractor_catalog_page(
        company=request.company, subcontractor=obj,
        page=request.GET.get("catalog_page") or 1,
        page_size=request.GET.get("catalog_size") or 10,
    )
    for offer in catalog.object_list:
        offer.freshness_key = freshness_key(offer.last_verified_at, policy=policy)
        offer.freshness_label = freshness_label(offer.freshness_key)
    qualification_qs = SourcingSubcontractorDocument.objects.for_company(request.company).filter(subcontractor=obj)
    today = timezone.localdate()
    from datetime import timedelta
    qualification_summary = qualification_qs.aggregate(
        total=Count("pk"),
        expired=Count("pk", filter=Q(expires_on__lt=today)),
        expiring=Count("pk", filter=Q(expires_on__gte=today, expires_on__lte=today + timedelta(days=30))),
        reviewed=Count("pk", filter=Q(review_status="approved") & (Q(expires_on__isnull=True) | Q(expires_on__gte=today))),
    )
    qualification_page = Paginator(qualification_qs.order_by("expires_on", "title", "id"), 10).get_page(request.GET.get("qualification_page", "1"))
    context.update(qualification_documents=qualification_page.object_list,
                   qualification_summary=qualification_summary, qualification_page=qualification_page)
    context.update(contacts=contacts, active_contacts=sum(1 for x in contacts if x.is_active),
                   contact_form=SourcingSubcontractorContactForm(),
                   history=subcontractor_history(company=request.company, subcontractor=obj),
                   service_count=obj.service_offers.filter(company=request.company).count(),
                   service_catalog_page=catalog,
                   catalog_page_sizes=SUBCONTRACTOR_CATALOG_PAGE_SIZES)
    return render(request, "sourcing/subcontractors/detail.html", context)


@login_required
def subcontractor_verify(request: HttpRequest, subcontractor_id) -> HttpResponse:
    _require_subcontractor_manage(request)
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    if obj.deleted_at or obj.archived_at or obj.status != SourcingEntityStatus.ACTIVE:
        raise PermissionDenied("Only active subcontractors can be verified.")
    form = SourcingSubcontractorVerificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            verify_subcontractor(
                actor_membership=_membership(request), subcontractor_id=obj.pk,
                contact_name=form.cleaned_data["contact_name"],
                note=form.cleaned_data["note"], request=request,
            )
        except ValidationError as exc:
            _apply_validation_error(form, exc)
        else:
            messages.success(request, "Company profile verification recorded. Service rates require separate verification.")
            return redirect("sourcing:subcontractor_detail", subcontractor_id=obj.pk)
    context = _subcontractor_context(request, obj, page_title="Verify Subcontractor Company")
    context.update(form=form)
    return render(request, "sourcing/subcontractors/verify.html", context,
                  status=400 if request.method == "POST" and form.errors else 200)


@login_required
def subcontractor_verification_history(request: HttpRequest, subcontractor_id) -> HttpResponse:
    _require_subcontractor_view(request)
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    page_obj = subcontractor_verification_page(
        company=request.company, subcontractor=obj, page=request.GET.get("page") or 1,
    )
    context = _subcontractor_context(request, obj, page_title="Company Verification History")
    context.update(page_obj=page_obj, entries=page_obj.object_list)
    return render(request, "sourcing/subcontractors/verification_history.html", context)


@login_required
def subcontractor_edit(request: HttpRequest, subcontractor_id) -> HttpResponse:
    _require_subcontractor_manage(request)
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id, deleted_at__isnull=True)
    if obj.archived_at:
        raise PermissionDenied("Restore the subcontractor before editing.")
    form = SourcingSubcontractorForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        try:
            obj = update_subcontractor(actor_membership=_membership(request), subcontractor_id=obj.pk, cleaned_data=form.cleaned_data, request=request)
        except ValidationError as exc:
            _apply_validation_error(form, exc)
        else:
            messages.success(request, "Subcontractor updated.")
            return redirect("sourcing:subcontractor_detail", subcontractor_id=obj.pk)
    context = _subcontractor_context(request, obj, page_title="Edit Subcontractor")
    context.update(form=form, submit_label="Save Changes")
    return render(request, "sourcing/subcontractors/form.html", context,
                  status=400 if request.method == "POST" and form.errors else 200)


def _subcontractor_action(request, subcontractor_id, action, success, **kwargs):
    if request.method != "POST":
        raise PermissionDenied("Subcontractor lifecycle changes require POST.")
    _require_subcontractor_manage(request)
    if not SourcingSubcontractor.objects.for_company(request.company).filter(pk=subcontractor_id).exists():
        raise Http404("Subcontractor not found.")
    try:
        action(actor_membership=_membership(request), subcontractor_id=subcontractor_id, request=request, **kwargs)
    except (ValidationError, SourcingSubcontractor.DoesNotExist) as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, success)
    return redirect("sourcing:subcontractor_detail", subcontractor_id=subcontractor_id)


@login_required
def subcontractor_status(request, subcontractor_id):
    return _subcontractor_action(request, subcontractor_id, set_subcontractor_status,
                                 "Subcontractor status updated.", status=request.POST.get("status", ""))


@login_required
def subcontractor_archive(request, subcontractor_id):
    return _subcontractor_action(request, subcontractor_id, archive_subcontractor,
                                 "Subcontractor archived.", reason=request.POST.get("reason", ""))


@login_required
def subcontractor_restore_archive(request, subcontractor_id):
    return _subcontractor_action(request, subcontractor_id, restore_subcontractor_archive, "Subcontractor restored from archive.")


@login_required
def subcontractor_trash(request, subcontractor_id):
    return _subcontractor_action(request, subcontractor_id, trash_subcontractor, "Subcontractor moved to Trash.",
                                 confirmation=request.POST.get("confirmation", ""), reason=request.POST.get("reason", ""))


@login_required
def subcontractor_restore_trash(request, subcontractor_id):
    return _subcontractor_action(request, subcontractor_id, restore_subcontractor_trash, "Subcontractor restored from Trash.")


@login_required
def subcontractor_delete(request, subcontractor_id):
    if request.method != "POST":
        raise PermissionDenied("Permanent deletion requires POST.")
    _require_subcontractor_manage(request)
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    try:
        delete_subcontractor(actor_membership=_membership(request), subcontractor_id=obj.pk,
                             confirmation=request.POST.get("confirmation", ""), reason=request.POST.get("reason", ""), request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
        return redirect("sourcing:subcontractor_detail", subcontractor_id=obj.pk)
    messages.success(request, "Subcontractor permanently deleted.")
    return redirect("sourcing:subcontractor_list")


@login_required
def subcontractor_contact_create(request, subcontractor_id):
    _require_subcontractor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Contact creation requires POST.")
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id, deleted_at__isnull=True)
    form = SourcingSubcontractorContactForm(request.POST)
    if form.is_valid():
        try:
            create_subcontractor_contact(actor_membership=_membership(request), subcontractor_id=obj.pk,
                                         cleaned_data=form.cleaned_data, request=request)
        except ValidationError as exc:
            _apply_validation_error(form, exc)
        else:
            messages.success(request, "Contact added.")
            return redirect("sourcing:subcontractor_detail", subcontractor_id=obj.pk)
    context = _subcontractor_context(request, obj, page_title="Add Contact")
    context.update(form=form, submit_label="Add Contact")
    return render(request, "sourcing/subcontractors/contact_form.html", context, status=400)


@login_required
def subcontractor_contact_edit(request, subcontractor_id, contact_id):
    _require_subcontractor_manage(request)
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id, deleted_at__isnull=True)
    if obj.archived_at:
        raise PermissionDenied("Restore the subcontractor before editing contacts.")
    contact = get_object_or_404(SourcingSubcontractorContact.objects.for_company(request.company), pk=contact_id, subcontractor=obj)
    form = SourcingSubcontractorContactForm(request.POST or None, instance=contact)
    if request.method == "POST" and form.is_valid():
        try:
            update_subcontractor_contact(actor_membership=_membership(request), subcontractor_id=obj.pk,
                                         contact_id=contact.pk, cleaned_data=form.cleaned_data, request=request)
        except ValidationError as exc:
            _apply_validation_error(form, exc)
        else:
            messages.success(request, "Contact updated.")
            return redirect("sourcing:subcontractor_detail", subcontractor_id=obj.pk)
    context = _subcontractor_context(request, obj, page_title="Edit Contact")
    context.update(form=form, submit_label="Save Contact")
    return render(request, "sourcing/subcontractors/contact_form.html", context,
                  status=400 if request.method == "POST" and form.errors else 200)


@login_required
def subcontractor_contact_deactivate(request, subcontractor_id, contact_id):
    _require_subcontractor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Contact deactivation requires POST.")
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    contact = get_object_or_404(SourcingSubcontractorContact.objects.for_company(request.company), pk=contact_id, subcontractor=obj)
    try:
        deactivate_subcontractor_contact(actor_membership=_membership(request), subcontractor_id=obj.pk, contact_id=contact.pk, request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Contact deactivated.")
    return redirect("sourcing:subcontractor_detail", subcontractor_id=obj.pk)


@login_required
def subcontractor_contact_delete(request, subcontractor_id, contact_id):
    _require_subcontractor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Contact deletion requires POST.")
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    contact = get_object_or_404(SourcingSubcontractorContact.objects.for_company(request.company), pk=contact_id, subcontractor=obj)
    try:
        delete_subcontractor_contact(actor_membership=_membership(request), subcontractor_id=obj.pk, contact_id=contact.pk, request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Contact deleted.")
    return redirect("sourcing:subcontractor_detail", subcontractor_id=obj.pk)


# Upgrade 04: independent Subcontractor Service Catalog (reference-only).
def _service_catalog_return(subcontractor_id):
    return f"{reverse('sourcing:subcontractor_detail', args=[subcontractor_id])}#service-catalog"


def _service_catalog_context(request, subcontractor, title, subtitle):
    context = _subcontractor_context(request, subcontractor, page_title=title)
    context.update(page_subtitle=subtitle, can_create_service=membership_can_manage_sourcing_masters(_membership(request)))
    return context


@login_required
def subcontractor_service_create(request: HttpRequest, subcontractor_id) -> HttpResponse:
    _require_subcontractor_manage(request)
    subcontractor = get_object_or_404(
        SourcingSubcontractor.objects.for_company(request.company).filter(
            deleted_at__isnull=True, archived_at__isnull=True), pk=subcontractor_id)
    if request.method == "POST":
        form = SourcingSubcontractorServiceForm(request.POST, company=request.company, subcontractor=subcontractor)
        if form.is_valid():
            try:
                create_service_offer(
                    actor_membership=_membership(request), subcontractor_id=subcontractor.pk,
                    cleaned_data={k: v for k, v in form.cleaned_data.items() if k not in {"verified_now", "contact_name"}},
                    verified_now=bool(form.cleaned_data.get("verified_now")),
                    contact_name=form.cleaned_data.get("contact_name") or "", request=request)
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Service capability added to Subcontractor Catalog.")
                return redirect(_service_catalog_return(subcontractor.pk))
    else:
        form = SourcingSubcontractorServiceForm(company=request.company, subcontractor=subcontractor)
    context = _service_catalog_context(request, subcontractor, "Add Service Capability", "Service scope, coverage and quotation reference.")
    context.update(form=form, submit_label="Add Service Capability")
    return render(request, "sourcing/subcontractors/service_form.html", context,
                  status=400 if request.method == "POST" and form.errors else 200)


@login_required
def subcontractor_service_edit(request: HttpRequest, subcontractor_id, offer_id) -> HttpResponse:
    _require_subcontractor_manage(request)
    subcontractor = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company).filter(
        deleted_at__isnull=True, archived_at__isnull=True), pk=subcontractor_id)
    offer = get_object_or_404(SourcingSubcontractorService.objects.for_company(request.company).select_related("service"),
                              pk=offer_id, subcontractor=subcontractor)
    if request.method == "POST":
        form = SourcingSubcontractorServiceForm(request.POST, instance=offer, company=request.company, subcontractor=subcontractor)
        if form.is_valid():
            try:
                update_service_offer(
                    actor_membership=_membership(request), subcontractor_id=subcontractor.pk, offer_id=offer.pk,
                    cleaned_data={k: v for k, v in form.cleaned_data.items() if k not in {"verified_now", "contact_name"}},
                    verified_now=bool(form.cleaned_data.get("verified_now")),
                    contact_name=form.cleaned_data.get("contact_name") or "", request=request)
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Service capability updated.")
                return redirect(_service_catalog_return(subcontractor.pk))
    else:
        form = SourcingSubcontractorServiceForm(instance=offer, company=request.company, subcontractor=subcontractor)
    context = _service_catalog_context(request, subcontractor, "Edit Service Capability", offer.service.name)
    context.update(form=form, offer=offer, submit_label="Save Service Capability")
    return render(request, "sourcing/subcontractors/service_form.html", context,
                  status=400 if request.method == "POST" and form.errors else 200)


@login_required
def subcontractor_service_verify(request: HttpRequest, subcontractor_id, offer_id) -> HttpResponse:
    _require_subcontractor_manage(request)
    subcontractor = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company).filter(
        deleted_at__isnull=True, archived_at__isnull=True), pk=subcontractor_id)
    offer = get_object_or_404(SourcingSubcontractorService.objects.for_company(request.company).select_related("service"),
                              pk=offer_id, subcontractor=subcontractor)
    if not offer.is_active:
        messages.error(request, "Reactivate this service capability before verifying it.")
        return redirect(_service_catalog_return(subcontractor.pk))
    if request.method == "POST":
        form = SourcingSubcontractorServiceVerifyForm(request.POST, instance=offer, subcontractor=subcontractor)
        if form.is_valid():
            try:
                verify_service_offer(
                    actor_membership=_membership(request), subcontractor_id=subcontractor.pk, offer_id=offer.pk,
                    cleaned_data={k: v for k, v in form.cleaned_data.items() if k != "contact_name"},
                    contact_name=form.cleaned_data.get("contact_name") or "", request=request)
            except ValidationError as exc:
                _apply_validation_error(form, exc)
            else:
                messages.success(request, "Service reference verified; previous values retained in history.")
                return redirect(_service_catalog_return(subcontractor.pk))
    else:
        form = SourcingSubcontractorServiceVerifyForm(instance=offer, subcontractor=subcontractor)
    context = _service_catalog_context(request, subcontractor, "Verify Service Reference", offer.service.name)
    context.update(form=form, offer=offer, submit_label="Confirm Verification", verify_mode=True)
    return render(request, "sourcing/subcontractors/service_form.html", context,
                  status=400 if request.method == "POST" and form.errors else 200)


@login_required
def subcontractor_service_history(request: HttpRequest, subcontractor_id, offer_id) -> HttpResponse:
    _require_subcontractor_view(request)
    subcontractor = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    offer = get_object_or_404(SourcingSubcontractorService.objects.for_company(request.company).select_related("service"),
                              pk=offer_id, subcontractor=subcontractor)
    page_obj = subcontractor_catalog_history_page(
        company=request.company, offer=offer,
        page=request.GET.get("page") or 1, page_size=request.GET.get("page_size") or 25)
    context = _service_catalog_context(request, subcontractor, "Service Verification History", offer.service.name)
    context.update(offer=offer, page_obj=page_obj, entries=page_obj.object_list,
                   page_sizes=SUBCONTRACTOR_HISTORY_PAGE_SIZES)
    return render(request, "sourcing/subcontractors/service_history.html", context)


@login_required
def subcontractor_service_status(request: HttpRequest, subcontractor_id, offer_id) -> HttpResponse:
    _require_subcontractor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Service Catalog status changes require POST.")
    get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    get_object_or_404(SourcingSubcontractorService.objects.for_company(request.company), pk=offer_id, subcontractor_id=subcontractor_id)
    try:
        set_service_offer_active(
            actor_membership=_membership(request), subcontractor_id=subcontractor_id, offer_id=offer_id,
            is_active=str(request.POST.get("active") or "").lower() in {"1", "true", "yes", "active"},
            request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Service Catalog status updated.")
    return redirect(_service_catalog_return(subcontractor_id))


@login_required
def subcontractor_service_delete(request: HttpRequest, subcontractor_id, offer_id) -> HttpResponse:
    _require_subcontractor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Service Catalog permanent removal requires POST.")
    get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    get_object_or_404(SourcingSubcontractorService.objects.for_company(request.company), pk=offer_id, subcontractor_id=subcontractor_id)
    try:
        result = delete_service_offer(
            actor_membership=_membership(request), subcontractor_id=subcontractor_id, offer_id=offer_id,
            confirmation=request.POST.get("confirmation") or "", request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, f"{result['label']} removed. Verification evidence preserved.")
    return redirect(_service_catalog_return(subcontractor_id))


# Upgrade 07 · Protected, independently reviewed subcontractor qualifications.


def _qualification_redirect(subcontractor_id):
    return reverse("sourcing:subcontractor_detail", args=[subcontractor_id]) + "#qualifications"


@login_required
def subcontractor_document_create(request: HttpRequest, subcontractor_id) -> HttpResponse:
    _require_subcontractor_manage(request)
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    if obj.archived_at or obj.deleted_at:
        raise PermissionDenied("Restore the subcontractor before changing qualifications.")
    form = SourcingSubcontractorDocumentForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data)
        upload = data.pop("upload", None)
        try:
            create_document(actor_membership=_membership(request), subcontractor_id=obj.pk,
                            cleaned_data=data, upload=upload, request=request)
        except ValidationError as exc:
            _apply_validation_error(form, exc)
        else:
            messages.success(request, "Qualification document uploaded for review.")
            return redirect(_qualification_redirect(obj.pk))
    ctx = _subcontractor_context(request, obj, page_title="Add Qualification")
    ctx.update(form=form, submit_label="Upload Qualification", qualification=None)
    return render(request, "sourcing/subcontractors/document_form.html", ctx,
                  status=400 if request.method == "POST" and form.errors else 200)


@login_required
def subcontractor_document_edit(request: HttpRequest, subcontractor_id, document_id) -> HttpResponse:
    _require_subcontractor_manage(request)
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    doc = get_object_or_404(SourcingSubcontractorDocument.objects.for_company(request.company),
                            subcontractor=obj, pk=document_id)
    if obj.archived_at or obj.deleted_at:
        raise PermissionDenied("Restore the subcontractor before changing qualifications.")
    form = SourcingSubcontractorDocumentForm(request.POST or None, instance=doc)
    if request.method == "POST" and form.is_valid():
        data = dict(form.cleaned_data)
        data.pop("upload", None)  # evidence file is immutable; upload a new document to replace
        try:
            update_document(actor_membership=_membership(request), subcontractor_id=obj.pk,
                            document_id=doc.pk, cleaned_data=data, request=request)
        except ValidationError as exc:
            _apply_validation_error(form, exc)
        else:
            messages.success(request, "Qualification details saved. Changes require re-review.")
            return redirect(_qualification_redirect(obj.pk))
    ctx = _subcontractor_context(request, obj, page_title="Edit Qualification")
    ctx.update(form=form, submit_label="Save Details", qualification=doc)
    return render(request, "sourcing/subcontractors/document_form.html", ctx,
                  status=400 if request.method == "POST" and form.errors else 200)


@login_required
def subcontractor_document_download(request: HttpRequest, subcontractor_id, document_id) -> HttpResponse:
    _require_subcontractor_view(request)
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    doc = get_object_or_404(SourcingSubcontractorDocument.objects.for_company(request.company),
                            subcontractor=obj, pk=document_id)
    try:
        stream = default_storage.open(doc.storage_key, "rb")
    except (OSError, FileNotFoundError):
        raise Http404("Document file unavailable.")
    response = FileResponse(stream, as_attachment=True, filename=doc.original_name, content_type=doc.content_type)
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
def subcontractor_document_review(request: HttpRequest, subcontractor_id, document_id) -> HttpResponse:
    _require_subcontractor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Qualification review requires POST.")
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    get_object_or_404(SourcingSubcontractorDocument.objects.for_company(request.company),
                      subcontractor=obj, pk=document_id)
    try:
        review_document(actor_membership=_membership(request), subcontractor_id=obj.pk,
                        document_id=document_id, status=request.POST.get("status", ""),
                        note=request.POST.get("note", ""), request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, "Qualification review recorded.")
    return redirect(_qualification_redirect(obj.pk))


@login_required
def subcontractor_document_delete(request: HttpRequest, subcontractor_id, document_id) -> HttpResponse:
    _require_subcontractor_manage(request)
    if request.method != "POST":
        raise PermissionDenied("Qualification removal requires POST.")
    obj = get_object_or_404(SourcingSubcontractor.objects.for_company(request.company), pk=subcontractor_id)
    get_object_or_404(SourcingSubcontractorDocument.objects.for_company(request.company),
                      subcontractor=obj, pk=document_id)
    try:
        delete_document(actor_membership=_membership(request), subcontractor_id=obj.pk,
                        document_id=document_id, confirmation=request.POST.get("confirmation", ""), request=request)
    except ValidationError as exc:
        messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    else:
        messages.success(request, "Qualification deleted; file scheduled for secure removal.")
    return redirect(_qualification_redirect(obj.pk))
