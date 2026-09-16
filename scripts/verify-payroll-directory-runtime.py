#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"PAYROLL DIRECTORY RUNTIME ERROR: {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    return path.read_text(encoding="utf-8")


version = text("VERSION").strip()
if version != "1.0.113":
    fail(f"VERSION must be 1.0.113, found {version!r}")

contract = json.loads(text("merge/payroll-directory-runtime.json"))
if contract.get("release") != version:
    fail("directory runtime contract does not match VERSION")
if contract.get("search_debounce_ms") != 320:
    fail("server-directory debounce must remain 320 ms")
required_kinds = {"branches", "departments", "employees", "projects", "suppliers", "workers"}
if set(contract.get("directories") or []) != required_kinds:
    fail("server-directory coverage changed")
required_guarantees = {
    "one-authoritative-request-per-directory",
    "abort-obsolete-search-request",
    "clear-loading-before-success-render",
    "preserve-last-valid-rows-during-refresh",
    "ignore-stale-response",
    "failed-request-does-not-auto-retry-loop",
    "explicit-retry-remains-available",
    "bounded-master-merge",
}
if not required_guarantees.issubset(set(contract.get("guarantees") or [])):
    fail("directory runtime guarantees are incomplete")

js = text("static/payroll/js/app.js")
for needle in (
    "async function appApi(url, { method = 'GET', body = null, signal = null } = {})",
    "if (signal) options.signal = signal;",
    "function cancelServerDirectoryRequest(kind,{clearPending=true}={})",
    "const controller=new AbortController();",
    "const payload=await appApi(request.url,{signal:controller.signal});",
    "if(error?.name==='AbortError') return store;",
    "const failed=store.failedKey===request.key;",
    "if(!current && !pending && !failed) queueMicrotask(()=>loadServerDirectory(kind));",
    "const rows=[...(store.results||[])];",
    "refreshing:!current && rows.length>0 && pending",
    "bindPayrollSearch(input,setter,{delay:320,beforeRender:()=>cancelServerDirectoryRequest(kind)});",
    "const indexById=new Map(collection.map((item,index)=>[item.id,index]));",
    "(rows || []).forEach(record => {",
    "employeeDirectoryCacheLimit: 250",
):
    if needle not in js:
        fail(f"directory runtime protection missing: {needle}")

# The completed response must clear loading before it redraws the active route.
success = re.search(
    r"directoryEntityMerge\(kind,store\.results\);(?P<body>.*?)if\(directoryRouteActive\(kind\)\) renderRoute\(\);",
    js,
    re.S,
)
if not success:
    fail("could not locate directory success lifecycle")
body = success.group("body")
if "store.pendingKey='';" not in body or "store.loading=false;" not in body or "store.controller=null;" not in body:
    fail("directory success lifecycle does not clear request/loading authority before rendering")
if body.index("store.loading=false;") > body.index("store.controller=null;"):
    fail("directory loading cleanup order changed unexpectedly")

bindings = {
    "branches": "bindServerDirectorySearch(branchSearch,'branches'",
    "departments": "bindServerDirectorySearch(departmentSearch,'departments'",
    "employees": "bindServerDirectorySearch(employeeSearch,'employees'",
    "projects": "bindServerDirectorySearch(projectSearch,'projects'",
    "suppliers": "bindServerDirectorySearch(supplierSearch,'suppliers'",
    "workers": "bindServerDirectorySearch(rentalSearch,'workers'",
}
for kind, needle in bindings.items():
    if needle not in js:
        fail(f"{kind} search is not using cancellation-aware server debounce")

if "data-directory-retry" not in js or "store.failedKey='';store.error='';loadServerDirectory(kind,{force:true});" not in js:
    fail("explicit failed-directory retry path is missing")

print("Verified Payroll server-directory runtime: 6 paged directories, AbortController cancellation, 320 ms search debounce, stale-row refresh and loading-state completion order.")
