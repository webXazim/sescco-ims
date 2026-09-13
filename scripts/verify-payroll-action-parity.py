#!/usr/bin/env python3
"""Verify that every registered Payroll mutation is wired to a real backend method.

This intentionally complements verify_payroll_frontend_contract.py.  The older gate proves
that browser URL strings resolve to mounted Django routes.  This gate goes further for
user-triggered mutations: each registered action must have visible client wiring, a bound
handler selector when applicable, a mounted backend view, and an HTTP method accepted by
that backend view's require_http_methods decorator.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "merge/payroll-action-parity.json"
JS_PATH = ROOT / "static/payroll/js/app.js"
URL_FILES = (
    ROOT / "apps/internal_payroll/urls.py",
    ROOT / "apps/rental_manpower/urls.py",
    ROOT / "apps/documents/urls.py",
    ROOT / "apps/core/api_urls.py",
)


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL ACTION PARITY ERROR: {message}")


def function_http_methods(path: Path, function_name: str) -> set[str]:
    try:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except FileNotFoundError:
        fail(f"backend source is missing: {path.relative_to(ROOT)}")
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != function_name:
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            name = decorator.func.id if isinstance(decorator.func, ast.Name) else None
            if name != "require_http_methods" or not decorator.args:
                continue
            try:
                values = ast.literal_eval(decorator.args[0])
            except (ValueError, TypeError, SyntaxError):
                fail(f"cannot read require_http_methods for {path.name}:{function_name}")
            return {str(value).upper() for value in values}
        fail(f"{path.relative_to(ROOT)}:{function_name} has no require_http_methods decorator")
    fail(f"backend function is missing: {path.relative_to(ROOT)}:{function_name}")
    return set()


def dataset_name(attr: str) -> str:
    parts = attr.split("-")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


try:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError) as exc:
    fail(f"cannot load {CONTRACT_PATH.relative_to(ROOT)}: {exc}")

rules = contract.get("rules")
if not isinstance(rules, list) or not rules:
    fail("contract has no rules")

js = JS_PATH.read_text(encoding="utf-8")
js_compact = re.sub(r"\s+", "", js)
url_text = "\n".join(path.read_text(encoding="utf-8") for path in URL_FILES)
seen_ids: set[str] = set()
checked_backends: set[tuple[str, str, str]] = set()
selector_attrs: set[str] = set()

for rule in rules:
    action_id = str(rule.get("id") or "").strip()
    if not action_id:
        fail("a contract rule has no id")
    if action_id in seen_ids:
        fail(f"duplicate action id: {action_id}")
    seen_ids.add(action_id)

    client_markers = rule.get("client")
    if not isinstance(client_markers, list) or not client_markers:
        fail(f"{action_id} has no client markers")
    for marker in client_markers:
        if not isinstance(marker, str) or not marker:
            fail(f"{action_id} contains an invalid client marker")
        marker_compact = re.sub(r"\s+", "", marker)
        present = marker in js or marker_compact in js_compact
        if not present and len(marker) >= 2 and marker[0] == marker[-1] and marker[0] in "\"'`":
            fragment = marker[1:-1]
            present = fragment in js or re.sub(r"\s+", "", fragment) in js_compact
        if not present:
            fail(f"{action_id} client wiring is missing marker: {marker}")
        data_match = re.match(r"data-([a-z0-9_-]+)", marker)
        if data_match:
            selector_attrs.add(data_match.group(1))

    backend = rule.get("backend") or {}
    rel = str(backend.get("file") or "").strip()
    function_name = str(backend.get("function") or "").strip()
    method = str(backend.get("method") or "").strip().upper()
    if not rel or not function_name or method not in {"POST", "PATCH", "PUT", "DELETE"}:
        fail(f"{action_id} has an invalid backend declaration")
    source = ROOT / rel
    key = (rel, function_name, method)
    if key not in checked_backends:
        allowed = function_http_methods(source, function_name)
        if method not in allowed:
            fail(f"{action_id} uses {method}, but {rel}:{function_name} allows {sorted(allowed)}")
        checked_backends.add(key)
    if function_name not in url_text:
        fail(f"{action_id} backend function is not mounted in Payroll URL configuration: {function_name}")

# A rendered data-* mutation marker is not enough: it must also participate in a JS selector
# or dataset handler.  This catches production-looking controls that have no click/change path.
for attr in sorted(selector_attrs):
    selector_marker = f"[data-{attr}"
    dataset_marker = f".dataset.{dataset_name(attr)}"
    if selector_marker not in js and dataset_marker not in js:
        fail(f"registered action data-{attr} is rendered but has no handler binding")

# Keep the high-risk workflow controls explicitly inside the parity registry.  New refactors can
# change implementation details, but removing one of these from the action contract must fail.
required_action_ids = {
    "internal.attendance.workflow",
    "internal.payroll.workflow",
    "internal.payment-batch.workflow",
    "internal.payment-batch.results",
    "internal.employee.lifecycle",
    "internal.employee.record-lifecycle",
    "rental.timesheet.workflow",
    "rental.settlement.workflow",
    "rental.supplier-payment.result",
    "rental.supplier-payment.retry",
    "rental.supplier.lifecycle",
    "rental.worker.lifecycle",
    "rental.project.lifecycle",
    "documents.finalize",
    "settings.company.update",
}
missing_required = sorted(required_action_ids - seen_ids)
if missing_required:
    fail(f"high-risk action contracts are missing: {missing_required}")

print(
    f"Verified {len(rules)} registered Payroll mutations across "
    f"{len(checked_backends)} backend method contracts and {len(selector_attrs)} bound action selectors."
)
