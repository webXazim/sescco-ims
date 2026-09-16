#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from time import perf_counter
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

RELEASE = "1.0.111"
VENDOR_CODE = "SDEMO-V00001"
MATERIAL_QUERY = "SDEMO Material 0001"
MANPOWER_CODE = "SDEMO-P00001"
TRADE_QUERY = "SDEMO Trade 001"
MAX_ROWS = 100


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run live Chromium E2E certification for SESCCO MS Sourcing Directory.")
    p.add_argument("--base-url", required=True, help="Application origin, e.g. https://ims.sescco.com")
    p.add_argument("--username", default=os.getenv("IMS_SOURCING_BROWSER_USERNAME", os.getenv("IMS_BROWSER_BENCHMARK_USERNAME", "")))
    p.add_argument("--password-env", default="IMS_SOURCING_BROWSER_PASSWORD")
    p.add_argument("--evidence", default="sourcing-browser-certification.json")
    p.add_argument("--max-settle-ms", type=int, default=10_000)
    p.add_argument("--headed", action="store_true")
    p.add_argument("--chromium-executable", default=os.getenv("IMS_BROWSER_CHROMIUM", ""))
    return p


def add_query(url: str, **params: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: str(value) for key, value in params.items()})
    return urlunparse(parsed._replace(query=urlencode(query)))


def main() -> int:
    args = parser().parse_args()
    username = args.username.strip()
    password = os.getenv(args.password_env, "") or os.getenv("IMS_BROWSER_BENCHMARK_PASSWORD", "")
    if not username:
        print("ERROR: --username / IMS_SOURCING_BROWSER_USERNAME / IMS_BROWSER_BENCHMARK_USERNAME is required.", file=sys.stderr)
        return 2
    if not password:
        print(f"ERROR: {args.password_env} (or IMS_BROWSER_BENCHMARK_PASSWORD fallback) is empty.", file=sys.stderr)
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - deployment utility dependency
        print(
            "ERROR: Playwright is required for live Sourcing browser certification. "
            "Install it in the release/test workstation and run `playwright install chromium`. "
            f"Import error: {exc}",
            file=sys.stderr,
        )
        return 2

    base = args.base_url.rstrip("/") + "/"
    marker = f"SOURCING-BROWSER-E2E-{int(time.time())}"
    evidence: dict[str, object] = {
        "release": RELEASE,
        "base_url": base,
        "seed_contract": {
            "vendor": VENDOR_CODE,
            "material_query": MATERIAL_QUERY,
            "manpower_supplier": MANPOWER_CODE,
            "trade_query": TRADE_QUERY,
        },
        "limits": {"max_rows": MAX_ROWS, "max_settle_ms": args.max_settle_ms},
        "verification_marker": marker,
        "scenarios": [],
        "browser_errors": [],
    }
    failures: list[str] = []
    browser_errors: list[str] = evidence["browser_errors"]  # type: ignore[assignment]

    def record(name: str, started: float, **values) -> None:
        elapsed = round((perf_counter() - started) * 1000, 1)
        evidence["scenarios"].append({"name": name, "elapsed_ms": elapsed, **values})  # type: ignore[union-attr]
        if elapsed > args.max_settle_ms:
            failures.append(f"{name} exceeded {args.max_settle_ms} ms: {elapsed} ms")

    executable = (args.chromium_executable or "").strip() or shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    launch_args: dict[str, object] = {"headless": not args.headed}
    if executable:
        launch_args["executable_path"] = executable

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_args)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(args.max_settle_ms)

        def page_error(exc) -> None:
            browser_errors.append(f"pageerror: {exc}")

        def console_message(msg) -> None:
            if msg.type == "error":
                browser_errors.append(f"console: {msg.text}")

        def bad_response(response) -> None:
            if response.status >= 500 and urlparse(response.url).netloc == urlparse(base).netloc:
                browser_errors.append(f"http {response.status}: {response.url}")

        page.on("pageerror", page_error)
        page.on("console", console_message)
        page.on("response", bad_response)

        started = perf_counter()
        page.goto(urljoin(base, "login/"), wait_until="domcontentloaded")
        page.locator('input[name="username"]').fill(username)
        page.locator('input[name="password"]').fill(password)
        page.locator('button[type="submit"]').click()
        page.wait_for_load_state("domcontentloaded")
        if "/login/" in page.url:
            failures.append("login did not leave /login/")
        record("login", started, url=page.url)

        def bounded_rows(name: str, selector: str) -> int:
            rows = page.locator(selector).count()
            if rows > MAX_ROWS:
                failures.append(f"{name} rendered {rows} rows (> {MAX_ROWS})")
            return rows

        def directory_search(path: str, query: str, expected_text: str, scenario: str) -> str:
            started = perf_counter()
            page.goto(urljoin(base, path), wait_until="domcontentloaded")
            search = page.locator('form.sourcing-toolbar input[name="q"]')
            search.wait_for(state="visible")
            search.fill(query)
            page.locator('form.sourcing-toolbar button[type="submit"]').click()
            page.wait_for_load_state("domcontentloaded")
            page.get_by_text(expected_text, exact=False).first.wait_for(state="visible")
            rows = bounded_rows(scenario, ".sourcing-table tbody tr")
            record(scenario, started, rows=rows, query=query)
            return page.url

        def rapid_finder(path: str, final_value: str, expected_text: str, scenario: str) -> None:
            started = perf_counter()
            page.goto(urljoin(base, path), wait_until="domcontentloaded")
            selector = '[data-sourcing-finder-root] form[data-sourcing-live-finder] input[name="q"]'
            search = page.locator(selector)
            search.wait_for(state="visible")
            for value in (final_value[:5], final_value[:10], final_value[:15], final_value):
                search.fill(value)
                page.wait_for_timeout(80)
            page.wait_for_timeout(1100)
            active = page.locator(selector)
            active.wait_for(state="visible")
            if active.input_value() != final_value:
                failures.append(f"{scenario} lost final rapid-search value")
            page.get_by_text(expected_text, exact=False).first.wait_for(state="visible")
            rows = bounded_rows(scenario, ".sourcing-table--finder tbody tr")
            record(scenario, started, rows=rows, query=final_value)

        def first_action_href(link_text: str) -> str:
            row = page.locator(".sourcing-table--finder tbody tr").filter(has=page.locator("details.sourcing-row-menu")).first
            row.locator("details.sourcing-row-menu summary").click()
            link = row.get_by_role("link", name=link_text, exact=True)
            href = link.get_attribute("href")
            if not href:
                failures.append(f"missing {link_text!r} action href")
                return ""
            return urljoin(base, href)

        def history_total() -> int:
            articles = page.locator(".sourcing-verification-timeline article").count()
            footer = page.locator(".sourcing-pagination > span")
            if footer.count():
                match = re.search(r"\bof\s+([\d,]+)\b", footer.first.inner_text())
                if match:
                    return int(match.group(1).replace(",", ""))
            return articles

        # Vendor Directory -> Vendor Supply Catalog.
        directory_search("app/sourcing/vendors/", VENDOR_CODE, VENDOR_CODE, "vendor-directory")
        started = perf_counter()
        vendor_row = page.locator(".sourcing-table tbody tr").filter(has_text=VENDOR_CODE).first
        vendor_row.locator(".sourcing-vendor-cell a").first.click()
        page.wait_for_load_state("domcontentloaded")
        page.locator('[data-sourcing-tab="catalog"]').click()
        page.locator('[data-sourcing-panel="catalog"]').wait_for(state="visible")
        vendor_catalog_rows = bounded_rows("vendor-supply-catalog", '[data-sourcing-panel="catalog"] .sourcing-table tbody tr')
        record("vendor-supply-catalog", started, rows=vendor_catalog_rows, vendor=VENDOR_CODE)

        # Material Finder -> history -> Verify -> immutable history evidence.
        rapid_finder("app/sourcing/material-finder/", MATERIAL_QUERY, MATERIAL_QUERY, "material-finder")
        history_url = first_action_href("Verification history")
        verify_url = first_action_href("Verify now")
        if not history_url or not verify_url:
            failures.append("material finder requires a sourcing.vendors.manage benchmark user")
        else:
            started = perf_counter()
            page.goto(add_query(history_url, page_size="100"), wait_until="domcontentloaded")
            page.get_by_role("heading", name="Verification History", exact=True).wait_for(state="visible")
            before = history_total()
            record("vendor-verification-history-before", started, revisions=before)

            started = perf_counter()
            page.goto(verify_url, wait_until="domcontentloaded")
            page.get_by_role("heading", name="Verify Supply Reference", exact=True).wait_for(state="visible")
            page.locator('input[name="contact_name"]').fill("Browser E2E Certification")
            page.locator('input[name="verification_note"]').fill(marker)
            page.get_by_role("button", name="Save Verification", exact=True).click()
            page.wait_for_load_state("domcontentloaded")
            record("vendor-quick-verification", started, return_url=page.url)

            started = perf_counter()
            page.goto(add_query(history_url, page_size="100"), wait_until="domcontentloaded")
            page.get_by_text(marker, exact=True).wait_for(state="visible")
            after = history_total()
            if after != before + 1:
                failures.append(f"vendor immutable history total did not increment exactly once: before={before}, after={after}")
            record("vendor-verification-history-after", started, revisions=after, marker=marker)

        # Manpower Directory -> Workforce Catalog.
        directory_search("app/sourcing/manpower-suppliers/", MANPOWER_CODE, MANPOWER_CODE, "manpower-directory")
        started = perf_counter()
        supplier_row = page.locator(".sourcing-table tbody tr").filter(has_text=MANPOWER_CODE).first
        supplier_row.locator(".sourcing-vendor-cell a").first.click()
        page.wait_for_load_state("domcontentloaded")
        page.locator('[data-sourcing-tab="workforce"]').click()
        page.locator('[data-sourcing-panel="workforce"]').wait_for(state="visible")
        workforce_rows = bounded_rows("manpower-workforce-catalog", '[data-sourcing-panel="workforce"] .sourcing-table tbody tr')
        record("manpower-workforce-catalog", started, rows=workforce_rows, supplier=MANPOWER_CODE)

        # Workforce Finder -> history -> Verify -> immutable history evidence.
        rapid_finder("app/sourcing/workforce-finder/", TRADE_QUERY, TRADE_QUERY, "workforce-finder")
        workforce_history_url = first_action_href("Verification history")
        workforce_verify_url = first_action_href("Verify now")
        if not workforce_history_url or not workforce_verify_url:
            failures.append("workforce finder requires a sourcing.manpower.manage benchmark user")
        else:
            started = perf_counter()
            page.goto(add_query(workforce_history_url, page_size="100"), wait_until="domcontentloaded")
            page.get_by_role("heading", name="Workforce Verification History", exact=True).wait_for(state="visible")
            before = history_total()
            record("workforce-verification-history-before", started, revisions=before)

            started = perf_counter()
            page.goto(workforce_verify_url, wait_until="domcontentloaded")
            page.get_by_role("heading", name="Verify Workforce Reference", exact=True).wait_for(state="visible")
            page.locator('input[name="contact_name"]').fill("Browser E2E Certification")
            page.locator('input[name="verification_note"]').fill(marker)
            page.get_by_role("button", name="Save Verification", exact=True).click()
            page.wait_for_load_state("domcontentloaded")
            record("workforce-quick-verification", started, return_url=page.url)

            started = perf_counter()
            page.goto(add_query(workforce_history_url, page_size="100"), wait_until="domcontentloaded")
            page.get_by_text(marker, exact=True).wait_for(state="visible")
            after = history_total()
            if after != before + 1:
                failures.append(f"workforce immutable history total did not increment exactly once: before={before}, after={after}")
            record("workforce-verification-history-after", started, revisions=after, marker=marker)

        browser.close()

    if browser_errors:
        failures.extend(browser_errors)
    evidence["failures"] = failures
    evidence["passed"] = not failures
    evidence_path = Path(args.evidence)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if failures:
        print("Sourcing browser E2E certification FAILED:", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        print(f"Evidence: {evidence_path}", file=sys.stderr)
        return 1
    print(f"Sourcing browser E2E certification passed. Evidence: {evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
