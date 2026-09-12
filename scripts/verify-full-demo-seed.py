#!/usr/bin/env python3
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"FULL DEMO SEED ERROR: {message}")


def require(rel: str, text: str) -> None:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing file: {rel}")
    value = path.read_text(encoding="utf-8")
    if text not in value:
        fail(f"{rel} missing required contract text: {text}")


seed_rel = "apps/core/management/commands/seed_payroll_test_data.py"
seed = (ROOT / seed_rel).read_text(encoding="utf-8")
ast.parse(seed)

# A --seed release must create both a live/draft period and a collision-safe finalized
# DEMO period so every server-generated payroll/report/output workflow can be exercised.
for text in (
    "def _safe_history_period(",
    "def _seed_internal_period(",
    "def _seed_rental_period(",
    "def _seed_lifecycle_scenarios(",
    "def _ensure_current_workflow_readiness(",
    "validate_period_for_submission(period=internal_period)",
    "validate_timesheet_for_submission(period=period)",
    "def _verify_report_coverage(",
    "def _verify_document_coverage(",
    "BusinessDocument",
    "calculate_payroll_run",
    "prepare_salary_payment_batch",
    "export_salary_payment_batch",
    "import_salary_payment_results",
    "close_salary_payment_batch",
    "DocumentType.INTERNAL_TIMESHEET",
    "DocumentType.SALARY_SLIP",
    "DocumentType.SALARY_PAYMENT_RECEIPT",
    "DocumentType.RENTAL_TIMESHEET",
    "DocumentType.SUPPLIER_SETTLEMENT",
    "DocumentType.SUPPLIER_INVOICE",
    "DocumentType.SUPPLIER_PAYMENT_RECEIPT",
    "DEMO-WPS-CSV",
    "DEMO-PAY-",
    "DEMO-INV-",
):
    require(seed_rel, text)

# Every report exposed by the three Payroll report workspaces must have deterministic data.
for text in (
    '"workforce-cost"',
    '"internal-payroll"',
    '"rental-project-cost"',
    '"supplier-cost"',
    '"overtime"',
    '"advances"',
    '"transfers"',
    '"payments"',
    '"wps"',
):
    require(seed_rel, text)

# Lifecycle fixtures must exercise temporary stop, final termination, Archive and 30-day Delete.
for text in (
    "DEMO-190", "DEMO-191", "DEMO-192", "DEMO-193", "DEMO-194", "DEMO-196", "DEMO-197",
    "DEMO-BR-ARCH", "DEMO-BR-DEL", "DEMO-DEP-ARCH", "DEMO-DEP-DEL",
    "RDEMO-090", "RDEMO-091", "RDEMO-092", "RDEMO-093", "RDEMO-094", "RDEMO-095", "RDEMO-096",
    "DEMO-SUP-INACTIVE", "DEMO-SUP-TERM", "DEMO-SUP-ARCH", "DEMO-SUP-DEL",
    "DEMO-HOLD", "DEMO-DONE", "DEMO-ARCH", "DEMO-DEL",
    'action="terminate"',
    'action="deactivate"',
):
    require(seed_rel, text)

# Rental termination/temporary-stop authority must be persisted and reachable from the UI/API.
for rel, text in (
    ("apps/internal_payroll/services/organization.py", '"stop_activity": EmploymentStatus.INACTIVE'),
    ("apps/rental_manpower/models/masters.py", 'TERMINATED = "terminated", "Terminated"'),
    ("apps/rental_manpower/models/masters.py", "termination_reason = models.CharField"),
    ("apps/rental_manpower/services/masters.py", "def _terminate_worker_locked("),
    ("apps/rental_manpower/services/masters.py", 'normalized in {"terminate","terminated"}'),
    ("apps/rental_manpower/services/masters.py", 'normalized in {"inactive","deactivate","stop_activity"}'),
    ("apps/rental_manpower/api.py", '"terminate","terminated","stop_activity"'),
    ("static/payroll/js/app.js", "Stop activity (temporary)"),
    ("static/payroll/js/app.js", "Terminate supplier relationship"),
    ("static/payroll/js/app.js", "Terminate worker"),
    ("static/payroll/js/app.js", "Terminate employment"),
    ("static/payroll/js/app.js", "['All','Active','Inactive','Terminated','Archived']"),
    ("static/payroll/js/app.js", "['All','Assigned','Scheduled','Available','Inactive','Terminated','Archived']"),
    ("scripts/release-tasks.sh", "seed_payroll_test_data"),
):
    require(rel, text)


frontend = (ROOT / "static/payroll/js/app.js").read_text(encoding="utf-8")

# The live Draft must be workflow-ready after lifecycle fixtures are introduced.
for rel, text in (
    (seed_rel, '"DEMO-190": D("3200")'),
    (seed_rel, '"DEMO-192": D("2800")'),
    (seed_rel, '"rental_worker_days_added"'),
    ("apps/rental_manpower/services/timesheets.py", "def validate_timesheet_for_submission("),
    ("apps/rental_manpower/services/timesheets.py", "A / N / L / OFF"),
    ("static/payroll/js/app.js", "function preferredRentalProjectId("),
    ("static/payroll/js/app.js", "A / L / S / H / OFF are valid explicit statuses; only blank required days block submission."),
    ("static/payroll/js/app.js", "A / N / L / OFF are valid explicit statuses; only blank assigned worker-days block submission."),
    ("static/payroll/js/app.js", "0 · Zero hours"),
    ("static/payroll/js/app.js", "A · Absent"),
):
    require(rel, text)

if "A · Sick absence" in frontend or "0 · Absent" in frontend:
    fail("rental attendance legend has regressed to the old incorrect code labels")
internal_create_start = frontend.find("'internal-employee': {")
branch_template_start = frontend.find("'branch': {", internal_create_start)
if internal_create_start < 0 or branch_template_start < 0:
    fail("internal employee create drawer boundary is missing")
if "['Active','On Leave','Inactive','Terminated']" in frontend[internal_create_start:branch_template_start]:
    fail("new Internal Employee drawer must use lifecycle termination instead of creating Terminated directly")

# Old restrictive temporary-stop behavior must not return.
for forbidden in (
    "Deactivate or release active workers before making this supplier inactive.",
    "Release the worker from current or scheduled assignments before making the worker inactive.",
    "Resolve the open assignment before reactivating this worker.",
):
    if forbidden in (ROOT / "apps/rental_manpower/services/masters.py").read_text(encoding="utf-8") or forbidden in (ROOT / "apps/rental_manpower/lifecycle.py").read_text(encoding="utf-8"):
        fail(f"obsolete restrictive stop-activity rule returned: {forbidden}")

# E2E cascade assertions compare freshly persisted parent/child recovery windows.
# Lifecycle services lock/refetch their own parent instance, so the seed must
# refresh its caller-held parent object after Delete before comparing timestamps.
for text in (
    "deleted_branch.refresh_from_db()",
    "deleted_department.refresh_from_db()",
    "deleted_supplier.refresh_from_db()",
):
    require(seed_rel, text)

for rel, text in (
    ("apps/core/trash.py", "def cascade_to_trash("),
    ("apps/core/trash.py", "def restore_trash_cascade("),
    ("apps/internal_payroll/services/organization.py", '"cascade_mode": "soft_delete_children"'),
    ("apps/rental_manpower/services/masters.py", '"cascade_mode":"soft_delete_children"'),
    ("apps/projects/services.py", '"cascade_mode": "soft_delete_inventory_children"'),
):
    require(rel, text)

print("Complete DEMO payroll/WPS/report/document + recoverable cascade + stop/termination seed contract verified.")
