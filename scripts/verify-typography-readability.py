#!/usr/bin/env python3
"""Static contract for readable text across four SESCCO application surfaces.

Browser-dependent computed-style checks are executed separately in staging.
This verifier does not alter authorization, model or layout contracts.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLE = "platform/css/typography-readability.css"
CSS = (ROOT / "static" / STYLE).read_text(encoding="utf-8")

layouts = {
    "Inventory": ("templates/base.html", "{% block extra_head %}{% endblock %}"),
    "Sourcing": ("templates/sourcing/base.html", "{% block extra_head %}{% endblock %}"),
    "Administration": ("templates/accounts/administration.html", "platform/css/access-management.css"),
    "Payroll": ("templates/payroll/app.html", "payroll/css/v2/payroll-controls.css"),
}
for module, (relative, previous_style) in layouts.items():
    html = (ROOT / relative).read_text(encoding="utf-8")
    assert STYLE in html, f"{module} missing shared readability stylesheet"
    assert html.index(STYLE) > html.index(previous_style), f"{module}: readability CSS must load last"

for selector in (
    ".access-form-alert", ".access-confirm__identity small", ".access-input",
    ".access-table td", ".access-permission-item small", ".access-field > label",
    ".inventory-shell-v2", ".sourcing-shell-v1 .sourcing-table td",
    ".ui-v2-root", ".data-table th", ".data-table td",
):
    assert selector in CSS, f"Readability contract missing: {selector}"
assert "@media screen" in CSS, "Readability layer must leave print styles unchanged"
assert "font-size: 14px" in CSS and "font-size: 12px" in CSS
print("PASS: Inventory, Sourcing, Administration and Payroll readable typography contracts verified.")
