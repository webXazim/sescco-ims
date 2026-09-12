#!/usr/bin/env python3
from pathlib import Path
import ast
import sys

ROOT = Path(__file__).resolve().parents[1]

def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL REFERENCE COVERAGE ERROR: {message}")

def require_text(rel: str, text: str) -> None:
    value = (ROOT / rel).read_text(encoding="utf-8")
    if text not in value:
        fail(f"{rel} is missing required contract text: {text}")

seed_path = ROOT / "apps/core/management/commands/seed_payroll_test_data.py"
seed_text = seed_path.read_text(encoding="utf-8")
ast.parse(seed_text)

for rel, text in [
    ("apps/core/models/settings.py", "commercial_registration = models.CharField"),
    ("apps/core/models/settings.py", "vat_number = models.CharField"),
    ("apps/core/models/settings.py", "document_address = models.CharField"),
    ("apps/core/models/settings.py", "document_letterhead = models.FileField"),
    ("apps/core/models/settings.py", "document_watermark = models.FileField"),
    ("apps/core/models/settings.py", "document_logo = models.FileField"),
    ("apps/internal_payroll/models/organization.py", "address = models.CharField(max_length=300, blank=True)"),
    ("apps/internal_payroll/models/payment.py", '"employee_address": "Employee address"'),
    ("apps/internal_payroll/services/payment.py", 'if "employee_address" in template_columns and not line.employee.address:'),
    ("templates/documents/print.html", "snapshot.issuer.vat_number"),
    ("templates/documents/print.html", "snapshot.employee.national_id"),
    ("templates/documents/print.html", "snapshot.components"),
    ("templates/documents/print.html", "Salary in Words"),
    ("templates/documents/print.html", "Salary Paid By"),
    ("templates/documents/print.html", "Employee Signature"),
    ("apps/documents/services/documents.py", "_amount_in_words"),
    ("apps/documents/services/documents.py", "document_letterhead"),
    ("apps/core/settings_api.py", "company_document_asset_api"),
    ("scripts/deploy-production.sh", "--seed"),
    ("scripts/release-tasks.sh", "seed_payroll_test_data"),
]:
    require_text(rel, text)


for rel, text in [
    ("apps/documents/urls.py", 'name="document-asset"'),
    ("templates/documents/print.html", "documents:document-asset"),
    ("apps/core/settings_api.py", 'X-Content-Type-Options'),
]:
    require_text(rel, text)

module = ast.parse(seed_text)
assignments = {}
for node in module.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        assignments[node.targets[0].id] = node.value
internal_node = assignments.get("INTERNAL_EMPLOYEES")
rental_node = assignments.get("RENTAL_WORKERS")
headers_node = assignments.get("WPS_HEADERS")
if not isinstance(internal_node, (ast.Tuple, ast.List)) or len(internal_node.elts) != 18:
    fail("seed must retain the 18 internal reference employees")
if not isinstance(rental_node, (ast.Tuple, ast.List)) or len(rental_node.elts) != 30:
    fail("seed must retain the 30 rental reference workers")
expected_headers = [
    "Bank", "Account Number", "Total Salary", "Transaction Reference", "Employee Name",
    "National ID/Iqama ID", "Employee Address", "Basic Salary", "Housing Allowance",
    "Other Earnings", "Deductions",
]
if not isinstance(headers_node, (ast.Tuple, ast.List)):
    fail("WPS_HEADERS constant is missing")
headers = [item.value for item in headers_node.elts if isinstance(item, ast.Constant) and isinstance(item.value, str)]
if headers != expected_headers:
    fail("WPS seed template no longer matches the supported source column contract")

# Seed fixtures must remain unmistakably synthetic and must never contain production WPS account data.
for forbidden in ("SA5810000011100491609405", "SA1220000003185539589940"):
    if forbidden in seed_text:
        fail("seed command contains a real uploaded account identifier")
for marker in ("DEMO-", "RDEMO-", "TEST DATA", "_demo_iban", "DEMO_BRANDING_PNG"):
    if marker not in seed_text:
        fail(f"seed safety marker missing: {marker}")

print("Payroll reference-document coverage + safe seed contract verified.")
