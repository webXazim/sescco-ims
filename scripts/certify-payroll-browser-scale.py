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
    p = argparse.ArgumentParser(description="Run live Chromium checks against SESCCO MS benchmark Payroll screens.")
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
        "release": "1.0.83",
        "base_url": base,
        "limits": {
            "max_table_rows": 100,
            "max_assignment_rows": 200,
            "max_global_results": 30,
            "max_settle_ms": args.max_settle_ms,
        },
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

        page.goto(urljoin(base, "login/"), wait_until="domcontentloaded")
        page.locator('input[name="username"]').fill(username)
        page.locator('input[name="password"]').fill(password)
        page.locator('button[type="submit"]').click()
        page.wait_for_load_state("domcontentloaded")
        if "/login/" in page.url:
            failures.append("login did not leave /login/")

        def open_route(workspace: str, route: str, wait_selector: str):
            started = perf_counter()
            page.goto(urljoin(base, f"payroll/?workspace={workspace}#/{route}"), wait_until="domcontentloaded")
            page.locator(wait_selector).wait_for(state="visible")
            return started

        def rapid_search(input_selector: str, final_value: str):
            locator = page.locator(input_selector)
            for value in (final_value[:2], final_value[:4], final_value[:6], final_value):
                locator.fill(value)
                page.wait_for_timeout(70)
            page.wait_for_timeout(900)
            if locator.input_value() != final_value:
                failures.append(f"{input_selector} lost the final rapid-search value")

        def bounded_rows(name: str, selector: str, max_rows: int = 100) -> int:
            rows = page.locator(selector).count()
            if max_rows == 100 and rows > 100:
                failures.append(f"{name} rendered {rows} rows (>100)")
            if max_rows == 200 and rows > 200:
                failures.append(f"{name} rendered {rows} rows (>200)")
            return rows

        def search_surface(*, name: str, workspace: str, route: str, input_selector: str, row_selector: str, query: str, max_rows: int = 100):
            started = open_route(workspace, route, input_selector)
            rapid_search(input_selector, query)
            page.wait_for_timeout(500)
            rows = bounded_rows(name, row_selector, max_rows=max_rows)
            record(name, started, rows=rows)
            return rows

        # Internal Company directory + attendance/overtime.
        search_surface(name="internal-employee-directory", workspace="internal", route="internal-employees", input_selector="#employeeSearch", row_selector=".employee-table tbody tr", query="DEMO")

        started = open_route("internal", "timesheets", "#timesheetSearch")
        rapid_search("#timesheetSearch", "DEMO")
        page.wait_for_timeout(500)
        attendance_rows = bounded_rows("internal-attendance", ".ui-v2-payroll-timesheet-workspace tbody tr")
        record("internal-attendance", started, rows=attendance_rows)
        sub_started = perf_counter()
        page.locator('[data-timesheet-tab="overtime"]').click()
        page.wait_for_timeout(500)
        overtime_rows = bounded_rows("internal-overtime", ".overtime-table tbody tr")
        record("internal-overtime", sub_started, rows=overtime_rows)

        # Salary Setup employee directory is lazy and independently server-paged.
        started = open_route("internal", "salary-setup", '[data-salary-tab="structures"]')
        page.locator('[data-salary-tab="structures"]').click()
        page.locator("#salaryStructureSearch").wait_for(state="visible")
        rapid_search("#salaryStructureSearch", "DEMO")
        page.wait_for_timeout(500)
        rows = bounded_rows("salary-setup-employee-structures", ".salary-structures-table tbody tr")
        record("salary-setup-employee-structures", started, rows=rows)

        # Payroll Run register + Review share the same bounded server page.
        started = open_route("internal", "payroll-runs", "#payrollSearch")
        rapid_search("#payrollSearch", "DEMO")
        page.wait_for_timeout(500)
        rows = bounded_rows("payroll-runs-register", ".payroll-table tbody tr")
        record("payroll-runs-register", started, rows=rows)
        review_button = page.locator("[data-payroll-view-review], [data-review-approve], [data-review-return]")
        if review_button.count():
            # Only click the explicit view toggle; workflow buttons are not mutated by certification.
            view = page.locator("[data-payroll-view-review]")
            if view.count():
                view.first.click()
                page.wait_for_timeout(500)
        review_started = perf_counter()
        review_rows = bounded_rows("payroll-runs-review", ".payroll-table tbody tr")
        record("payroll-runs-review", review_started, rows=review_rows)

        search_surface(name="internal-advances-adjustments", workspace="internal", route="adjustments", input_selector="#adjustmentSearch", row_selector=".adjustment-ledger-table tbody tr", query="DEMO")

        # Salary payment register is expected in the benchmark seed.
        search_surface(name="salary-payments-register", workspace="internal", route="payments", input_selector="#paymentSearch", row_selector=".payment-table tbody tr", query="DEMO")
        search_surface(name="bank-readiness", workspace="internal", route="bank-export", input_selector="#bankExportSearch", row_selector=".bank-payment-register tbody tr", query="DEMO")
        search_surface(name="wps-readiness", workspace="internal", route="wps", input_selector="#wpsSearch", row_selector=".wps-table tbody tr", query="DEMO")

        # Shared records/reporting surfaces added in 1.0.76.
        search_surface(name="documents", workspace="internal", route="documents", input_selector="#documentSearch", row_selector=".document-list-item", query="DEMO")
        started = open_route("internal", "reports", "#reportSearch")
        wps_report = page.locator('[data-report-type="wps"]')
        wps_report.click()
        page.locator('[data-report-type="wps"].is-active').wait_for(state="visible")
        rapid_search("#reportSearch", "DEMO")
        page.wait_for_timeout(500)
        rows = bounded_rows("reports", ".report-table tbody tr")
        record("reports", started, rows=rows, report_type="wps")
        search_surface(name="archive", workspace="internal", route="archive", input_selector="#recordManagementSearch", row_selector=".records-bin-page table tbody tr", query="DEMO")
        search_surface(name="delete-recovery", workspace="internal", route="trash", input_selector="#recordManagementSearch", row_selector=".records-bin-page table tbody tr", query="DEMO")

        started = open_route("management", "management-approvals", "#managementApprovalPageSize")
        rows = bounded_rows("management-approval-center", ".management-approval-item")
        record("management-approval-center", started, rows=rows)
        search_surface(name="management-audit-trail", workspace="management", route="management-audit", input_selector="#managementAuditSearch", row_selector=".management-audit-row", query="DEMO")

        # Rental directory and all three assignment lifecycle views.
        search_surface(name="rental-workforce-directory", workspace="rental", route="rental-workforce", input_selector="#rentalSearch", row_selector=".rental-worker-table tbody tr", query="RDEMO")

        search_surface(name="rental-worker-adjustments", workspace="rental", route="adjustments", input_selector="#adjustmentSearch", row_selector=".adjustment-ledger-table tbody tr", query="RDEMO")

        started = open_route("rental", "rental-assignments", "#rentalAssignmentSearch")
        rapid_search("#rentalAssignmentSearch", "RDEMO")
        page.wait_for_timeout(500)
        rows = bounded_rows("rental-assignment-activity", "table tbody tr", max_rows=200)
        record("rental-assignment-activity", started, rows=rows)
        sub_started = perf_counter()
        page.locator('[data-assignment-tab="deployment"]').click()
        page.wait_for_timeout(500)
        rows = bounded_rows("rental-current-deployment", ".assignment-deployment-table tbody tr")
        record("rental-current-deployment", sub_started, rows=rows)
        sub_started = perf_counter()
        page.locator('[data-assignment-tab="pool"]').click()
        page.wait_for_timeout(500)
        rows = bounded_rows("rental-supplier-pool", ".assignment-workspace-tabs ~ section table tbody tr")
        record("rental-supplier-pool", sub_started, rows=rows)

        # Rental daily timesheet + overtime are both bounded to the selected project page.
        started = open_route("rental", "timesheets", "#rentalTimesheetSearch")
        rapid_search("#rentalTimesheetSearch", "RDEMO")
        page.wait_for_timeout(500)
        rows = bounded_rows("rental-project-timesheets", ".ui-v2-payroll-timesheet-workspace tbody tr")
        record("rental-project-timesheets", started, rows=rows)
        sub_started = perf_counter()
        page.locator('[data-rental-timesheet-tab="ot"]').click()
        page.wait_for_timeout(500)
        rows = bounded_rows("rental-overtime", ".ui-v2-prs-rental-ot-table tbody tr")
        record("rental-overtime", sub_started, rows=rows)

        # Global Ctrl/Cmd+K search remains bounded to 5 per six entity types.
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
