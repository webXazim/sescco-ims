from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.sourcing.models import (
    SourcingAvailability,
    SourcingEntityStatus,
    SourcingManpowerSupplier,
    SourcingMaterial,
    SourcingRateBasis,
    SourcingTrade,
    SourcingVendor,
    SourcingVendorOffer,
    SourcingWorkforceOffer,
)

SEED_PREFIX = "SDEMO-"


@dataclass(frozen=True, slots=True)
class SourcingScaleProfile:
    name: str
    vendors: int
    materials: int
    vendor_offers: int
    manpower_suppliers: int
    trades: int
    workforce_offers: int


SCALE_PROFILES = {
    "functional": SourcingScaleProfile("functional", 50, 25, 100, 25, 20, 75),
    "realistic": SourcingScaleProfile("realistic", 2_000, 500, 10_000, 1_000, 100, 5_000),
    "benchmark": SourcingScaleProfile("benchmark", 10_000, 2_000, 50_000, 5_000, 250, 25_000),
}


def get_scale_profile(name: str) -> SourcingScaleProfile:
    try:
        return SCALE_PROFILES[str(name or "").strip().lower()]
    except KeyError as exc:
        raise ValidationError({"profile": "Use functional, realistic, or benchmark."}) from exc


def _bulk_create(model, rows: Iterable, *, batch_size: int) -> int:
    payload = list(rows)
    if not payload:
        return 0
    model.objects.bulk_create(payload, batch_size=batch_size, ignore_conflicts=True)
    return len(payload)


def _refuse_mixed_company(company, *, allow_mixed: bool) -> None:
    if allow_mixed:
        return
    checks = (
        SourcingVendor.objects.for_company(company).exclude(code__startswith=SEED_PREFIX).exists(),
        SourcingMaterial.objects.for_company(company).exclude(code__startswith=SEED_PREFIX).exists(),
        SourcingManpowerSupplier.objects.for_company(company).exclude(code__startswith=SEED_PREFIX).exists(),
        SourcingTrade.objects.for_company(company).exclude(code__startswith=SEED_PREFIX).exists(),
    )
    if any(checks):
        raise ValidationError(
            {"profile": "Sourcing scale seed refused because non-SDEMO sourcing masters already exist. Use a disposable test company/database or pass --allow-mixed-scale-seed explicitly."}
        )


def seed_sourcing_scale_data(*, company, profile: SourcingScaleProfile, batch_size: int = 5000, allow_mixed: bool = False) -> dict[str, int]:
    if profile.name != "functional":
        _refuse_mixed_company(company, allow_mixed=allow_mixed)
    now = timezone.now()
    batch_size = max(100, min(int(batch_size or 5000), 10_000))

    with transaction.atomic():
        existing_vendor_codes = set(
            SourcingVendor.objects.for_company(company).filter(code__startswith=SEED_PREFIX).values_list("code", flat=True)
        )
        _bulk_create(
            SourcingVendor,
            (
                SourcingVendor(
                    company=company,
                    code=f"{SEED_PREFIX}V{i:05d}",
                    name=f"SDEMO Vendor {i:05d}",
                    normalized_name=f"sdemo vendor {i:05d}",
                    display_name=f"SDEMO Vendor {i:05d}",
                    primary_contact_name=f"Vendor Contact {i:05d}",
                    phone=f"+96655{i:07d}"[-13:],
                    email=f"vendor{i:05d}@sdemo.invalid",
                    city=("Dammam", "Jubail", "Riyadh", "Jeddah")[i % 4],
                    region=("Eastern Province", "Eastern Province", "Riyadh", "Makkah")[i % 4],
                    status=SourcingEntityStatus.ACTIVE,
                    last_verified_at=now - timedelta(days=i % 45),
                    notes="SDEMO synthetic sourcing benchmark vendor",
                )
                for i in range(1, profile.vendors + 1)
                if f"{SEED_PREFIX}V{i:05d}" not in existing_vendor_codes
            ),
            batch_size=batch_size,
        )

        existing_material_codes = set(
            SourcingMaterial.objects.for_company(company).filter(code__startswith=SEED_PREFIX).values_list("code", flat=True)
        )
        _bulk_create(
            SourcingMaterial,
            (
                SourcingMaterial(
                    company=company,
                    code=f"{SEED_PREFIX}M{i:04d}",
                    name=f"SDEMO Material {i:04d}",
                    normalized_name=f"sdemo material {i:04d}",
                    category=("Civil", "Electrical", "Mechanical", "HVAC", "Safety")[i % 5],
                    default_unit=("EA", "M", "KG", "TON")[i % 4],
                    aliases=[f"SDEMO-MAT-{i:04d}"],
                    normalized_aliases=f"sdemo-mat-{i:04d}",
                    is_active=True,
                    notes="SDEMO synthetic sourcing benchmark material",
                )
                for i in range(1, profile.materials + 1)
                if f"{SEED_PREFIX}M{i:04d}" not in existing_material_codes
            ),
            batch_size=batch_size,
        )

        vendors = list(SourcingVendor.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}V").order_by("code")[: profile.vendors])
        materials = list(SourcingMaterial.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}M").order_by("code")[: profile.materials])
        offers_per_vendor = max(1, profile.vendor_offers // max(1, profile.vendors))
        offer_rows = []
        for vi, vendor in enumerate(vendors):
            for offset in range(offers_per_vendor):
                if len(offer_rows) >= profile.vendor_offers:
                    break
                material = materials[(vi * offers_per_vendor + offset) % len(materials)]
                offer_rows.append(
                    SourcingVendorOffer(
                        company=company,
                        vendor=vendor,
                        material=material,
                        specification=f"SDEMO spec {offset + 1}",
                        brand="SDEMO",
                        model=f"V{vi % 100:02d}-{offset + 1}",
                        available_quantity=Decimal((vi + offset) % 500 + 1),
                        unit=material.default_unit,
                        availability=(SourcingAvailability.AVAILABLE if offset % 4 else SourcingAvailability.LIMITED),
                        rate=Decimal("10.0000") + Decimal((vi + offset) % 900),
                        currency="SAR",
                        lead_time=f"{(offset % 7) + 1} day(s)",
                        last_verified_at=now - timedelta(days=(vi + offset) % 45),
                        verification_note="SDEMO benchmark verification",
                        is_active=True,
                    )
                )
        _bulk_create(SourcingVendorOffer, offer_rows, batch_size=batch_size)

        existing_supplier_codes = set(
            SourcingManpowerSupplier.objects.for_company(company).filter(code__startswith=SEED_PREFIX).values_list("code", flat=True)
        )
        _bulk_create(
            SourcingManpowerSupplier,
            (
                SourcingManpowerSupplier(
                    company=company,
                    code=f"{SEED_PREFIX}P{i:05d}",
                    name=f"SDEMO Manpower Supplier {i:05d}",
                    normalized_name=f"sdemo manpower supplier {i:05d}",
                    primary_contact_name=f"Manpower Contact {i:05d}",
                    phone=f"+96654{i:07d}"[-13:],
                    email=f"manpower{i:05d}@sdemo.invalid",
                    city=("Dammam", "Jubail", "Riyadh", "Jeddah")[i % 4],
                    region=("Eastern Province", "Eastern Province", "Riyadh", "Makkah")[i % 4],
                    status=SourcingEntityStatus.ACTIVE,
                    last_verified_at=now - timedelta(days=i % 45),
                    notes="SDEMO synthetic sourcing benchmark manpower supplier",
                )
                for i in range(1, profile.manpower_suppliers + 1)
                if f"{SEED_PREFIX}P{i:05d}" not in existing_supplier_codes
            ),
            batch_size=batch_size,
        )

        existing_trade_codes = set(
            SourcingTrade.objects.for_company(company).filter(code__startswith=SEED_PREFIX).values_list("code", flat=True)
        )
        _bulk_create(
            SourcingTrade,
            (
                SourcingTrade(
                    company=company,
                    code=f"{SEED_PREFIX}T{i:03d}",
                    name=f"SDEMO Trade {i:03d}",
                    normalized_name=f"sdemo trade {i:03d}",
                    category=("Civil", "Electrical", "Mechanical", "HVAC", "Engineering")[i % 5],
                    aliases=[f"SDEMO-WORKER-{i:03d}"],
                    normalized_aliases=f"sdemo-worker-{i:03d}",
                    is_active=True,
                    notes="SDEMO synthetic sourcing benchmark trade",
                )
                for i in range(1, profile.trades + 1)
                if f"{SEED_PREFIX}T{i:03d}" not in existing_trade_codes
            ),
            batch_size=batch_size,
        )

        suppliers = list(SourcingManpowerSupplier.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}P").order_by("code")[: profile.manpower_suppliers])
        trades = list(SourcingTrade.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}T").order_by("code")[: profile.trades])
        offers_per_supplier = max(1, profile.workforce_offers // max(1, profile.manpower_suppliers))
        workforce_rows = []
        for si, supplier in enumerate(suppliers):
            for offset in range(offers_per_supplier):
                if len(workforce_rows) >= profile.workforce_offers:
                    break
                trade = trades[(si * offers_per_supplier + offset) % len(trades)]
                workforce_rows.append(
                    SourcingWorkforceOffer(
                        company=company,
                        supplier=supplier,
                        trade=trade,
                        available_quantity=(si + offset) % 80 + 1,
                        availability=(SourcingAvailability.AVAILABLE if offset % 4 else SourcingAvailability.LIMITED),
                        rate=Decimal("1200.0000") + Decimal((si + offset) % 6500),
                        currency="SAR",
                        rate_basis=SourcingRateBasis.MONTH,
                        overtime_rate=Decimal("15.0000") + Decimal(offset),
                        mobilization_lead_time=f"{(offset % 7) + 1} day(s)",
                        work_location=("Eastern Province", "KSA", "Jubail", "Dammam")[offset % 4],
                        last_verified_at=now - timedelta(days=(si + offset) % 45),
                        verification_note="SDEMO benchmark workforce verification",
                        is_active=True,
                    )
                )
        _bulk_create(SourcingWorkforceOffer, workforce_rows, batch_size=batch_size)

    counts = {
        "vendors": SourcingVendor.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}V").count(),
        "materials": SourcingMaterial.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}M").count(),
        "vendor_offers": SourcingVendorOffer.objects.for_company(company).filter(vendor__code__startswith=f"{SEED_PREFIX}V").count(),
        "manpower_suppliers": SourcingManpowerSupplier.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}P").count(),
        "trades": SourcingTrade.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}T").count(),
        "workforce_offers": SourcingWorkforceOffer.objects.for_company(company).filter(supplier__code__startswith=f"{SEED_PREFIX}P").count(),
    }
    expected = {
        "vendors": profile.vendors,
        "materials": profile.materials,
        "vendor_offers": profile.vendor_offers,
        "manpower_suppliers": profile.manpower_suppliers,
        "trades": profile.trades,
        "workforce_offers": profile.workforce_offers,
    }
    missing = [f"{key}={counts[key]}<{value}" for key, value in expected.items() if counts[key] < value]
    if missing:
        raise ValidationError({"profile": "Sourcing scale seed did not reach requested volume: " + ", ".join(missing)})
    return counts
