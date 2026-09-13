# Payroll mutation and data authority

SESCCO MS Payroll treats Django/PostgreSQL as the authority for business records. Browser memory is a render/cache layer only, and `localStorage` is limited to UI preferences such as workspace, period, filters, selected views and page sizes.

## Stale response rule

A server mutation must never be overwritten in the browser by an older GET that was already in flight. The Payroll client therefore maintains generation counters for Internal Attendance, Internal Payroll, Salary Payments, Rental Timesheets and Rental Settlements. A loader captures a generation ticket before its request and discards the response if a newer server payload has superseded that generation.

Salary-payment and Rental-settlement payloads are additionally period-activated: responses for a period that is no longer selected may be cached, but they cannot replace the active period's finance arrays.

## Browser storage rule

The authoritative allowlist is `merge/payroll-data-authority.json`. Adding a new Payroll `localStorage` key requires an explicit contract update and the key must remain in the `payroll-ui-*` namespace. Payroll masters, attendance/timesheet entries, payroll calculations, adjustments, settlements, payments, documents and lifecycle records must never be serialized into browser storage.

`python scripts/verify-payroll-data-authority.py` enforces these rules and is part of the Payroll frontend and production-freeze gates.
