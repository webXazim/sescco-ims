#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from time import perf_counter
from urllib.parse import urljoin


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run live Chromium checks against SESCCO MS benchmark Payroll screens."
    )
    p.add_argument("--base-url", required=True, help="Application origin, e.g. https://ims.sescco.com")
    p.add_argument("--username", default=os.getenv("IMS_BROWSER_BENCHMARK_USERNAME", ""))
    p.add_argument("--password-env", default="IMS_BROWSER_BENCHMARK_PASSWORD")
    p.add_argument("--evidence", default="payroll-browser-certification.json")
    p.add_argument("--max-settle-ms", type=int, default=10_000)
    p.add_argument("--headed", action="store_true")
    p.add_argument("--chromium-executable", default=os.getenv("IMS_BROWSER_CHROMIUM", ""), help="Optional Chromium/Chrome executable path; auto-detected when available.")
    return p


def main() -> int:
    args = parser().parse_args()
    username = args.username.strip()
    password = os.getenv(args.password_env, "")
    if not username:
        print("ERROR: --username or IMS_BROWSER_BENCHMARK_USERNAME is required.", file=sys.stderr)
        return 2
    if not password:
        print(f"ERROR: password environment variable {args.password_env} is empty.", file=sys.stderr)
        return 2

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - deployment utility dependency
        print(
            "ERROR: Playwright is required for the live browser certification. "
            "Install it in a release/test workstation and run `playwright install chromium`. "
            f"Import error: {exc}",
            file=sys.stderr,
        )
        return 2

    base = args.base_url.rstrip("/") + "/"
    evidence: dict[str, object] = {
        "release": "1.0.70",
        "base_url": base,
        "limits": {"max_table_rows": 100, "max_global_results": 30, "max_settle_ms": args.max_settle_ms},
        "scenarios": [],
    }
    failures: list[str] = []

    def record(name: str, started: float, **values):
        elapsed = round((perf_counter() - started) * 1000, 1)
        row = {"name": name, "elapsed_ms": elapsed, **values}
        evidence["scenarios"].append(row)
        if elapsed > args.max_settle_ms:
            failures.append(f"{name} exceeded {args.max_settle_ms} ms: {elapsed} ms")
        return row

    executable = (args.chromium_executable or "").strip() or shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
    launch_args = {"headless": not args.headed}
    if executable:
        launch_args["executable_path"] = executable

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_args)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(args.max_settle_ms)

        # Sign in through the real Django login form so company/workspace permissions are real.
        page.goto(urljoin(base, "login/"), wait_until="domcontentloaded")
        page.locator('input[name="username"]').fill(username)
        page.locator('input[name="password"]').fill(password)
        page.locator('button[type="submit"]').click()
        page.wait_for_load_state("domcontentloaded")
        if "/login/" in page.url:
            failures.append("login did not leave /login/")

        def open_route(workspace: str, route: str, input_selector: str):
            started = perf_counter()
            page.goto(
                urljoin(base, f"payroll/?workspace={workspace}#/{route}"),
                wait_until="domcontentloaded",
            )
            page.locator(input_selector).wait_for(state="visible")
            return started

        def rapid_search(input_selector: str, final_value: str):
            locator = page.locator(input_selector)
            for value in (final_value[:2], final_value[:4], final_value[:6], final_value):
                locator.fill(value)
                page.wait_for_timeout(70)
            page.wait_for_timeout(900)
            if locator.input_value() != final_value:
                failures.append(f"{input_selector} lost the final rapid-search value")

        # Internal Attendance / OT: bounded table, rapid server search and pagination.
        started = open_route("internal", "timesheets", "#timesheetSearch")
        page.wait_for_timeout(350)
        rapid_search("#timesheetSearch", "DEMO")
        page.wait_for_timeout(500)
        internal_rows = page.locator(".ui-v2-payroll-timesheet-workspace tbody tr").count()
        if internal_rows > 100:
            failures.append(f"Internal Attendance rendered {internal_rows} rows (>100)")
        if page.get_by_text("Loading attendance page…", exact=True).count():
            failures.append("Internal Attendance remained in loading state")
        next_button = page.locator('[data-timesheet-page][aria-label="Next page"]:not([disabled])')
        if next_button.count():
            next_button.first.click()
            page.wait_for_timeout(700)
        record("internal-attendance-rapid-search-page", started, rows=internal_rows)

        # Assignment Lifecycle: Activity page is bounded to 100 segments / <=200 expanded events.
        started = open_route("rental", "rental-assignments", "#rentalAssignmentSearch")
        rapid_search("#rentalAssignmentSearch", "RDEMO")
        page.wait_for_timeout(500)
        assignment_rows = page.locator("table tbody tr").count()
        if assignment_rows > 200:
            failures.append(f"Assignment Lifecycle rendered {assignment_rows} rows (>200)")
        if page.get_by_text("Loading assignment data…", exact=True).count():
            failures.append("Assignment Lifecycle remained in loading state")
        assignment_next = page.locator('[data-assignment-page^="activity|"]:not([disabled])')
        if assignment_next.count() >= 2:
            assignment_next.nth(1).click()
            page.wait_for_timeout(700)
        record("rental-assignment-rapid-search-page", started, rows=assignment_rows)

        # Rental Project Timesheet: project-period roster only, <=100 rows.
        started = open_route("rental", "timesheets", "#rentalTimesheetSearch")
        rapid_search("#rentalTimesheetSearch", "RDEMO")
        page.wait_for_timeout(500)
        rental_rows = page.locator(".ui-v2-payroll-timesheet-workspace tbody tr").count()
        if rental_rows > 100:
            failures.append(f"Rental Timesheet rendered {rental_rows} rows (>100)")
        if page.get_by_text("Loading timesheet page…", exact=True).count():
            failures.append("Rental Timesheet remained in loading state")
        rental_next = page.locator('[data-rental-timesheet-page][aria-label="Next page"]:not([disabled])')
        if rental_next.count():
            rental_next.first.click()
            page.wait_for_timeout(700)
        record("rental-timesheet-rapid-search-page", started, rows=rental_rows)

        # Global Ctrl/Cmd+K-equivalent search remains bounded to 5 per 6 entity types.
        started = perf_counter()
        page.locator("#globalSearchButton").click()
        page.locator("#globalSearchInput").fill("RDEMO")
        page.wait_for_timeout(1100)
        result_count = page.locator("#commandResults [data-search-route]").count()
        if result_count > 30:
            failures.append(f"Global search returned {result_count} results (>30)")
        if page.get_by_text("Searching server…", exact=True).count():
            failures.append("Global search remained in loading state")
        record("global-server-search", started, results=result_count)

        context.close()
        browser.close()

    evidence["ok"] = not failures
    evidence["failures"] = failures
    out = Path(args.evidence)
    out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1
    print("Live Payroll browser-scale certification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
