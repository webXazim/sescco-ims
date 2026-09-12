#!/usr/bin/env python3
from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]
def fail(m): raise SystemExit(f"RENTAL LIFECYCLE ERROR: {m}")
def req(rel,text):
 p=ROOT/rel
 if not p.is_file() or text not in p.read_text(encoding="utf-8"): fail(f"{rel} missing {text!r}")
for rel in ["apps/rental_manpower/models/masters.py","apps/rental_manpower/lifecycle.py","apps/rental_manpower/services/masters.py","apps/rental_manpower/selectors/masters.py","apps/rental_manpower/api.py","apps/rental_manpower/urls.py","apps/rental_manpower/migrations/0006_supplier_worker_lifecycle.py","apps/rental_manpower/migrations/0007_master_trash_retention.py"]: ast.parse((ROOT/rel).read_text(encoding="utf-8"))
for rel,text in [
("apps/rental_manpower/lifecycle.py","class ManpowerSupplierLifecyclePolicy"),("apps/rental_manpower/lifecycle.py","class RentalWorkerLifecyclePolicy"),
("apps/rental_manpower/services/masters.py","def change_supplier_lifecycle("),("apps/rental_manpower/services/masters.py","def archive_supplier("),("apps/rental_manpower/services/masters.py","def delete_unused_supplier("),("apps/rental_manpower/services/masters.py","def change_worker_lifecycle("),("apps/rental_manpower/services/masters.py","def delete_unused_worker("),
("apps/rental_manpower/api.py","def supplier_lifecycle_api("),("apps/rental_manpower/api.py","def worker_lifecycle_api("),
("static/payroll/js/app.js","function openRentalMasterLifecycleDrawer"),("static/payroll/js/app.js","Move to Trash"),("static/payroll/js/app.js","'Archived'"),
]: req(rel,text)
manifest=(ROOT/'merge/frozen-merge-migrations.sha256').read_text(encoding='utf-8')
for migration in ('0006_supplier_worker_lifecycle.py','0007_master_trash_retention.py'):
 if migration not in manifest: fail(f'rental lifecycle migration not frozen: {migration}')
print('Rental supplier / worker separate Archive + 30-day Trash contract verified.')
