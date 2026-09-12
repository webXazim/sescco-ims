#!/usr/bin/env python3
from pathlib import Path

REPORTS = (
    Path("apps/core/management/commands/merge_internal_payroll_report.py"),
    Path("apps/core/management/commands/merge_rental_manpower_report.py"),
)

for path in REPORTS:
    text = path.read_text(encoding="utf-8")
    required = 'relation_scope = model.objects.filter(**{f"{field.name}__isnull": False})'
    if required not in text:
        raise SystemExit(f"{path}: nullable company-owned relations are not scoped before tenant comparison")
    forbidden = 'model.objects.exclude(**{f"{field.name}__company_id": F("company_id")}).count()'
    if forbidden in text:
        raise SystemExit(f"{path}: nullable relation reconciliation can still report false cross-company errors")

payment_model = Path("apps/rental_manpower/models/settlements.py").read_text(encoding="utf-8")
for required in (
    'if self.retry_of_id:',
    'Retry payment must belong to the same company.',
    'Retry payment must belong to the same supplier.',
):
    if required not in payment_model:
        raise SystemExit(f"SupplierPayment retry tenant guard missing: {required}")

print("Tenant reconciliation nullable-relation contract verified.")
