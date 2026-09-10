#!/usr/bin/env python3
"""Static contract check between the frozen Payroll browser client and merged Django URLs."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "static/payroll/js/app.js").read_text(encoding="utf-8")
URL_FILES = [
    ROOT / "apps/internal_payroll/urls.py",
    ROOT / "apps/rental_manpower/urls.py",
    ROOT / "apps/documents/urls.py",
    ROOT / "apps/core/api_urls.py",
]


def django_routes() -> list[tuple[str, re.Pattern[str]]]:
    routes: list[tuple[str, re.Pattern[str]]] = []
    for file in URL_FILES:
        text = file.read_text(encoding="utf-8")
        for match in re.finditer(r"path\(\s*[\"']([^\"']+)[\"']", text):
            raw = "/" + match.group(1)
            parts = re.split(r"(<[^>]+>)", raw)
            regex = "".join(r"[^/]+" if part.startswith("<") else re.escape(part) for part in parts)
            routes.append((raw, re.compile(r"^" + regex + r"$")))
    return routes


def frontend_urls() -> list[str]:
    urls: set[str] = set()
    patterns = (
        r"'(/(?:api|documents)/[^']*)'",
        r'"(/(?:api|documents)/[^"]*)"',
        r"`(/(?:api|documents)/[^`]*)`",
    )
    for pattern in patterns:
        for body in re.findall(pattern, JS):
            body = body.split("?", 1)[0]
            body = re.sub(r"\$\{[^}]+\}", "__id__", body)
            urls.add(body)
    return sorted(urls)


routes = django_routes()
client_urls = frontend_urls()
missing = [url for url in client_urls if not any(pattern.fullmatch(url) for _, pattern in routes)]

if missing:
    print("Payroll frontend URLs without a merged Django route:")
    for url in missing:
        print(f"  - {url}")
    raise SystemExit(1)

required_prefixes = {
    "/api/internal/",
    "/api/rental/",
    "/api/documents/",
    "/api/management/",
    "/api/reports/",
    "/api/settings/",
    "/documents/",
}
seen = {prefix for prefix in required_prefixes if any(url.startswith(prefix) for url in client_urls)}
missing_prefixes = sorted(required_prefixes - seen)
if missing_prefixes:
    raise SystemExit(f"Payroll client no longer references expected API domains: {missing_prefixes}")

print(f"Verified {len(client_urls)} Payroll browser URL contracts against {len(routes)} Django routes.")
