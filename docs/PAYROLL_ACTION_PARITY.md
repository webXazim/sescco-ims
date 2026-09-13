# Payroll frontend/backend action parity

SESCCO MS 1.0.58 freezes a machine-readable contract for user-triggered Payroll mutations.

The contract is stored in `merge/payroll-action-parity.json`. Each action identifies the browser wiring markers and the Django function/method that owns the mutation. `scripts/verify-payroll-action-parity.py` validates four boundaries before release:

1. the browser action still exists;
2. rendered `data-*` action controls are bound through a selector or dataset handler;
3. the backend function is still mounted in Payroll URL configuration; and
4. the browser mutation method is explicitly accepted by the backend `require_http_methods` decorator.

This gate supplements `verify_payroll_frontend_contract.py`, which validates browser URL resolution and the existing lifecycle/data-authority contracts. Both run through `scripts/verify-payroll-frontend.sh`; the action-parity verifier also runs from the production-freeze verifier.

The registry intentionally includes Internal organization/employees, attendance, payroll, adjustments, salary setup, salary payments/WPS, Rental suppliers/projects/workers, assignment lifecycle, timesheets, settlements, supplier payments, Documents finalization, company settings/branding, and Archive/Delete-bin restore actions.

When a new production mutation control is added, add its contract entry in the same upgrade. A UI-only mutation control or an HTTP-method mismatch must fail release verification rather than becoming a silent runtime defect.
