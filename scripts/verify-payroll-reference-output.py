#!/usr/bin/env python3
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL REFERENCE OUTPUT ERROR: {message}")


def require_text(rel: str, text: str) -> None:
    value = (ROOT / rel).read_text(encoding="utf-8")
    if text not in value:
        fail(f"{rel} is missing required output-parity contract: {text}")


# Keep the amount-in-words engine dependency-free so this verifier can run before Django/image build.
amount_path = ROOT / "apps/documents/services/amounts.py"
spec = importlib.util.spec_from_file_location("payroll_amount_words", amount_path)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
if module.money_to_words("2415.00", "SAR") != "Two Thousand Four Hundred Fifteen Saudi Riyals Only":
    fail("SAR salary-in-words output no longer matches the reference business requirement")
if module.money_to_words("5666.61", "SAR") != "Five Thousand Six Hundred Sixty Six Saudi Riyals and Sixty One Halalas Only":
    fail("halala amount-in-words output is incorrect")

for rel, text in [
    ("apps/core/models/settings.py", "document_branding_mode = models.CharField"),
    ("apps/core/models/settings.py", "document_logo = models.FileField"),
    ("apps/core/models/settings.py", "document_letterhead = models.FileField"),
    ("apps/core/models/settings.py", "document_watermark = models.FileField"),
    ("apps/core/migrations/0003_company_document_branding.py", "Full-page letterhead"),
    ("apps/core/settings_api.py", "company_branding_asset_api"),
    ("apps/core/settings_api.py", "Upload a PNG, JPEG or WebP image."),
    ("apps/core/services/settings.py", "must not delete the previous file"),
    ("apps/documents/services/documents.py", '"salary_in_words"'),
    ("apps/documents/services/documents.py", '"paid_by": "Bank"'),
    ("apps/documents/services/documents.py", '"storage_key": field.name'),
    ("apps/documents/views.py", "Historical branding asset integrity verification failed."),
    ("templates/documents/print.html", "Salary in words"),
    ("templates/documents/print.html", "Salary Paid By"),
    ("templates/documents/print.html", "Employee Signature"),
    ("templates/documents/print.html", "Manager"),
    ("templates/documents/print.html", "paper--letterhead"),
    ("static/payroll/js/app.js", "brandingAssetTemplate"),
    ("static/payroll/js/app.js", "uploadBrandAsset"),
    ("static/payroll/js/app.js", "documentBrandingMode"),
    ("apps/core/management/commands/seed_payroll_test_data.py", "_seed_document_branding"),
    ("apps/core/management/commands/seed_payroll_test_data.py", "DEMO-letterhead.png"),
    ("templates/payroll/app.html", "?v=1.0.36"),
]:
    require_text(rel, text)

# The seed must continue to contain safe synthetic fixtures, never uploaded banking identifiers.
seed_text = (ROOT / "apps/core/management/commands/seed_payroll_test_data.py").read_text(encoding="utf-8")
ast.parse(seed_text)
for forbidden in ("SA5810000011100491609405", "SA1220000003185539589940", "2587580594", "2440420111"):
    if forbidden in seed_text:
        fail("seed command contains a real uploaded bank/identity value")

print("Payroll reference salary-slip + branding output contract verified.")
