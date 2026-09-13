# Payroll Output E2E Contract — 1.0.60

SESCCO MS 1.0.60 freezes the output side of Payroll after lifecycle/data-authority completion.

The gate covers server-generated reports and filtered CSV export, Internal salary-payment/WPS batch preparation/export/reconciliation/retry/close/reopen, Rental settlement and supplier-payment lifecycle, and all seven immutable final payroll document types. Supplier profile finance/document actions must deep-link into the real filtered server-backed workspaces; placeholder output tiles/toasts are not allowed.

`python3 scripts/verify-payroll-output-e2e.py` is part of both the Payroll frontend verification and packaged production-freeze verification.
