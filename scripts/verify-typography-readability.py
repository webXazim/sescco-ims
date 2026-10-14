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

# Administration is a multi-section page. The Access Profiles table must not
# inherit nowrap cells or the Users-only mobile column-hiding rules.
admin_template = (ROOT / "templates/accounts/administration.html").read_text(encoding="utf-8")
admin_js = (ROOT / "static/platform/js/access-management.js").read_text(encoding="utf-8")
for marker in (
    'id="accessCurrentSection"', 'id="profiles"', 'id="history"',
    'access-profile-col-coverage', 'access-profile-col-count',
):
    assert marker in admin_template, f"Administration section/column marker missing: {marker}"
for marker in (
    "syncFromHash", "setActiveSection", "aria-current", "access-coverage-list",
    "access-permission-count", "window.addEventListener('scroll'",
):
    assert marker in admin_js, f"Administration navigation/profile markup missing: {marker}"
for marker in (
    ".access-profile-table td", ".access-coverage-tag", ".access-permission-count",
    "scroll-margin-top: 74px", ".access-profile-table :is(th, td):nth-child(3)",
):
    assert marker in CSS, f"Administration layout rule missing: {marker}"

print("PASS: Inventory, Sourcing, Administration and Payroll readable typography contracts and profile navigation verified.")
