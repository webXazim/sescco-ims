# 1.0.64 — Production freeze / release candidate

- Freezes the SESCCO MS Payroll integration sequence after the 1.0.58 frontend/backend action-parity, 1.0.59 server data-authority, 1.0.60 output E2E, 1.0.61 scale-seed, 1.0.62 performance, and 1.0.63 production-E2E certification upgrades.
- Adds `merge/release-candidate.json` and `scripts/verify-release-candidate.py` to bind the final release identity, the exact 1.0.63 predecessor archive checksum, required static/runtime gates, supported seed profiles and canonical deployment entrypoint.
- Carries the frozen Payroll production-E2E contract forward to release 1.0.64 and requires the release-candidate verifier from both the packaged production-freeze gate and the production release-task pipeline.
- Updates Payroll static cache-busters and package documentation to 1.0.64 without changing Payroll formulas, database schema, lifecycle semantics, permissions or user-facing workflow behavior.
- Runtime certification remains mandatory in the isolated Docker/PostgreSQL rehearsal environment: deployment checks, zero migration drift, the curated Payroll E2E Django suite, and the full Django regression suite must pass before production cutover.
- Regenerates the complete source/configuration SHA-256 production freeze after all final release metadata and verification changes.

# 1.0.63 — Full Payroll production E2E certification

- Adds a single frozen production-E2E certification contract at `merge/payroll-production-e2e.json` spanning 11 high-risk scenarios and 75 critical existing Django regression tests across Internal Payroll, Rental Manpower, Documents and platform access boundaries.
- Adds `scripts/certify-payroll-production-e2e.sh`, which first verifies the frozen certification contract, then runs `check --deploy`, rejects migration drift, and executes the curated 13-label Django Payroll suite against Django's isolated test database.
- Certification coverage explicitly includes owner/officer authorization and forbidden access, attendance status normalization/submission, payroll review/approval integrity, WPS/payment reconciliation, Rental assignment/timesheet/settlement/payment workflows, invalid transitions, lifecycle/archive/delete/restore recovery, reports/documents, tenant isolation, benchmark seed shape and performance regression guards.
- Adds `scripts/verify-payroll-production-e2e.py` and a Django contract wrapper. The static verifier fails if a required scenario loses its referenced regression test, a prerequisite release verifier disappears, or the runtime/rehearsal certification path is removed.
- Wires the production-E2E contract into Payroll frontend verification, release tasks and the production-freeze gate. Production rehearsal now runs the dedicated certification suite separately and stores `payroll-e2e-certification.txt` as evidence before the full Django regression suite.
- No Payroll calculation formula, schema, or user-facing workflow is changed in this certification release. The 1.0.62 query hardening and 1.0.61 benchmark profiles remain intact.
- The package can statically verify certification completeness in environments without Django; runtime certification remains mandatory in the release/rehearsal environment where Django/PostgreSQL are available.

# 1.0.62 — Payroll performance & query hardening

- Converts the highest-cardinality Internal Payroll calculation sources from per-employee database access to set-wise locked loads for organization assignments, salary structures/lines, attendance entries and overtime snapshots while preserving the existing transaction and `SELECT FOR UPDATE` authority.
- Makes Internal Attendance roster rendering prefetch effective salary structures and salary lines so overtime readiness does not issue salary queries per employee; overtime save/submission validation also resolves effective structures and base components set-wise.
- Reworks Payroll calculation snapshot creation to validate generated line/component/adjustment objects in memory and persist them with bounded `bulk_create` batches. Snapshot fingerprint verification now fetches line children set-wise instead of querying components and adjustments for every Payroll line.
- Removes an O(workers × assignments) Rental Timesheet roster scan by grouping effective assignments by worker before segment construction.
- Hardens Rental settlement context by loading supplier scopes for all project-periods in one query and reusing the already-loaded adjustment set. Settlement snapshot lines/rates/adjustments are persisted in bounded batches and fingerprint verification groups child rows set-wise.
- Adds `python manage.py payroll_performance_report` with SQL query counting and elapsed-time diagnostics for Internal Attendance, Internal Payroll preflight, the largest Rental project timesheet and Rental settlement context. `--fail-on-query-budget` enforces the release query budgets (40 queries per measured Internal/Rental path by default).
- Adds `merge/payroll-performance.json`, `scripts/verify-payroll-performance.py` and a Django regression wrapper, and wires the static performance contract into the production-freeze gate so cardinality-dependent query patterns cannot silently return.
- Keeps the 1.0.61 functional/realistic/benchmark seed profiles unchanged. No schema migration is required; the high-volume query shapes use the existing Payroll indexes and uniqueness constraints.

# 1.0.61 — Large test & benchmark Payroll seed profiles

- Keeps the existing `functional` DEMO seed as the default and adds explicit `realistic` and `benchmark` volume profiles without changing production Payroll behavior.
- Adds a realistic profile with 250 Internal employees, 750 Rental workers, 6 branches, 12 departments, 8 suppliers, 12 projects and six months of scale history.
- Adds a benchmark profile with 2,000 Internal employees, 5,000 Rental workers, 15 branches, 24 departments, 30 suppliers, 40 projects and twelve months of scale history.
- Seeds high-cardinality daily Internal Attendance and Rental Timesheet rows, overtime, approved advances/adjustments, closed Payroll snapshots, WPS salary-payment rows, worker transfer history, supplier settlements, settlement lines and paid supplier-payment allocations.
- Uses stable `DEMO-SCALE-*` / `RDEMO-SCALE-*` identities, unique financial references, conflict-safe bulk inserts and post-seed population verification so interrupted large seeds can be resumed safely by rerunning the same profile.
- Makes scale seeding monotonic: `benchmark` expands an existing `realistic` dataset, while later smaller-profile runs never shrink or rewrite the larger benchmark history.
- Keeps the canonical functional Draft + closed E2E month separate from scale history so benchmark rows do not change the known workflow fixture used for functional testing.
- Blocks `realistic` / `benchmark` on a tenant containing non-DEMO Internal employees or Rental workers to prevent accidental benchmark pollution of production-like payroll data.
- Adds `--seed-profile functional|realistic|benchmark` to production deploy/release scripts, plus `IMS_SEED_PROFILE` and `IMS_SEED_BATCH_SIZE` operator controls.
- Adds a frozen scale-seed contract, regression coverage, operator documentation and a production-freeze verifier. No database migration is required.

# 1.0.60 — Payroll reports, WPS, payments and documents E2E completion

- Freezes the Payroll output path after the 1.0.58 action-parity and 1.0.59 data-authority upgrades: server-generated reports, Internal WPS/salary-payment reconciliation, Rental supplier settlement/payment finance, and immutable final documents are now covered by one release contract.
- Replaces the supplier-profile payment/document shortcuts with real finance drill-downs. Supplier payment rows open the authoritative payment detail, the Payments workspace opens pre-filtered to that supplier, and the supplier Documents tab renders actual finalized Django document records instead of static placeholder tiles.
- Makes report CSV export match the visible report search filter by sending the active search query to the backend export endpoint and filtering the authoritative server report rows before CSV serialization. Existing spreadsheet-formula neutralization remains in force.
- Adds `merge/payroll-output-e2e.json` and `scripts/verify-payroll-output-e2e.py`, covering 12 workspace/report routes, 6 Internal payment/WPS endpoints, 6 Rental settlement/payment endpoints and all 7 final document types.
- The output verifier rejects a return of the old supplier-settlement placeholder toast and enforces document eligibility gates: Locked timesheets, Approved-or-later settlements, and Paid payment receipts.
- Adds a Django `SimpleTestCase` wrapper for the output verifier and wires the gate into both Payroll frontend verification and the packaged production-freeze verification. Existing 80-mutation action parity, 30-key browser-storage authority, 67 URL contracts and complete DEMO report/WPS/document seed coverage remain intact.
- No database migration or payroll-calculation formula change is required.

# 1.0.59 — Payroll mutation and data authority completion

- Makes the browser explicitly a cache/render layer for Payroll business data; Django/PostgreSQL remains authoritative for masters, attendance/timesheets, payroll calculations, adjustments, settlements, payments, documents and lifecycle state.
- Adds generation-based stale-response protection for Internal Attendance, Internal Payroll, Salary Payments, Rental Timesheets and Rental Settlements. A slow GET that started before a newer server mutation is now discarded instead of overwriting the mutation result in browser memory.
- Hardens Salary Payments period switching so an older-period response may be cached but cannot replace the active period's payment/template/readiness arrays. Cached periods are re-activated deliberately when selected again.
- Hardens Rental Settlements the same way: period-specific settlement/financial snapshots remain cached by period, while active adjustment/payment/timesheet-scope arrays are only activated for the currently selected period.
- Captures Rental Timesheet project/period scope before loading and only re-renders when that same scope is still active, preventing late project/period responses from hijacking the visible sheet.
- Removes obsolete empty browser persistence placeholders for Rental Timesheets, Rental Overtime, Supplier Payments, Rental Worker state and Rental Settlements so future work cannot mistake them for supported persistence paths.
- Adds `merge/payroll-data-authority.json`, documenting the 30 allowed `payroll-ui-*` browser-storage keys. These are UI preferences/selections only; business ledgers and master records are forbidden from localStorage.
- Adds `scripts/verify-payroll-data-authority.py`, a Django regression wrapper, and production/frontend release gates that enforce browser-storage scope plus stale-response guards across the five authoritative domains.
- No database migration is required. Existing server-side lifecycle, calculation and payment semantics remain unchanged.

# 1.0.58 — Payroll frontend/backend action parity

- Adds a machine-readable Payroll mutation contract at `merge/payroll-action-parity.json` covering 80 user-triggered Internal Payroll, Rental Manpower, Documents and Payroll Settings mutations.
- Adds `scripts/verify-payroll-action-parity.py`, which proves every registered mutation still has visible client wiring, handler-bound `data-*` controls where applicable, a mounted Django backend function, and the exact POST/PATCH/DELETE method accepted by that function's `require_http_methods` contract.
- Extends the existing frontend verification beyond URL existence. The previous gate still verifies 67 browser URL contracts; the new gate additionally verifies 80 mutations against 73 backend method contracts and 40 bound action selectors.
- Explicitly protects multi-action workflow controls including attendance submit/return, payroll calculate/reset/review/approve/return, payment prepare/export/start/cancel/import/close/reopen/retry, Rental timesheet submit/return, settlement calculate/return/close, supplier payment result/retry, lifecycle Archive/Delete/Restore, and Archive/Delete-bin restore.
- Adds a Django regression test that runs the action-parity verifier inside the normal test suite and fails if high-risk Payroll actions leave the registry.
- Wires the action-parity gate into both `verify-payroll-frontend.sh` and the production-freeze verifier so a production-looking button can no longer ship merely because its URL happens to exist.
- No database migration or payroll calculation change is required; this upgrade hardens the UI-to-backend execution contract before the 1.0.59 mutation/data-authority pass.

# 1.0.57 — Archive/Delete/Restore cascading integrity

- Hardens the existing 30-day recoverable Delete model for Branch / Office, Department, Internal Employee, Manpower Supplier, Rental Worker and shared Project without turning historical payroll, attendance, timesheet, settlement, payment, inventory movement, document or audit records into destructive cascades. Parent-owned operational child masters continue to share the exact parent recovery window and restore atomically through `TrashCascadeLink`.
- Fixes lifecycle API recovery for independently restored child records. An Internal Employee restored while its Branch/Department parent is still deleted, or a Rental Worker restored while its Manpower Supplier parent remains deleted, now returns a successful payload with the inherited parent Delete state instead of re-querying only currently visible rows and reporting an error after the restore succeeded.
- Makes Project Archive/Delete an explicit inherited **assignment operational boundary** rather than falsely deleting the permanent Rental Worker master. Current effective-dated assignments remain intact for history/recovery; worker payloads now publish project lifecycle/operational state and assignment payloads retain project identity even when the deleted project is absent from the active project directory.
- Updates the Rental Worker profile so a deleted/archived/on-hold project is shown as a retained assignment boundary. Transfer and Release remain available for safe recovery/redeployment, while project-local Trade/Rate changes are suppressed until the project is active again. Deleted projects are not exposed as broken profile links.
- Corrects an outdated Internal API regression test that expected Department Delete not to soft-delete its current employee child; the test now enforces the same parent/child `deleted_at` and `purge_after` window used by the production service. Adds explicit API regressions for independent child restore under a deleted parent and a Rental project delete/restore regression proving the worker master and exact assignment survive.
- Extends the packaged Payroll contract gate so future releases fail if inherited child recovery, project assignment lifecycle authority, or exact cascade test coverage is removed. No database migration is required.

# 1.0.56 — Rental Manpower lifecycle completion

- Makes the Rental settlement/project lifecycle backend-authoritative from locked timesheet through calculation, review, approval, supplier payment, and project-period closure. Project contexts now publish `allowedActions`, `nextAction`, and explicit action gates; the browser no longer derives settlement actions from display labels.
- Makes supplier-payment result handling backend-authoritative. Payment rows now publish allowed result actions, retry eligibility, and receipt eligibility; the UI consumes those permissions for Paid/Failed/Cancelled/Reversed transitions and retry instead of inferring them from status text.
- Advances `SupplierSettlement.revision` on review submission, return/rejection, approval, payment-status synchronization, and closure in addition to calculation, preserving a complete authoritative state-change sequence for downstream finance/document workflows. Canonical service aliases such as `submit_for_review`, `return_for_changes`, `close_period`, and payment result `complete` are accepted without changing stored lifecycle values.
- Tightens Return for Changes so a project settlement group can only return when every supplier snapshot is in Review, preventing a mixed-state project group from partially rewinding.
- Preserves historical finance completion after operational stop boundaries: terminating a supplier/worker or completing a project continues to block new operational assignments while already-approved settlement snapshots remain payable, documentable, reversible/retryable where allowed, and closable.
- Confirms supplier invoice generation remains limited to Approved-or-later settlement snapshots and supplier payment receipts remain limited to Paid supplier payments; those document checks stay server enforced.
- Extends the settlement progress display through Payment and Closed states and removes the unused browser `rentalSettlementHasDrift()` placeholder that falsely hardcoded no drift. Adds regression/static release coverage for lifecycle authority, revisions, document gates, and historical-finance continuity.
- No database migration is required.

# 1.0.55 — Internal Payroll lifecycle completion

- Makes the Internal Payroll Run workflow backend-authoritative from calculation through review and approval. The period context now publishes allowed actions and explicit `canCalculate`, `canReset`, `canSubmitReview`, `canReturnForChanges`, and `canApprove` gates; the browser renders actions from that contract instead of inferring permission from display labels.
- Advances `PayrollRun.revision` on every authoritative lifecycle mutation: calculation/recalculation, reset, review submission, return/rejection, approval, payment-processing start, Paid transition, Close, and Reopen. Workflow aliases such as `submit for review` and `reject` normalize at the service boundary without changing stored statuses.
- Makes salary-payment batch actions backend-authoritative. Payment responses now publish `allowedActions`, `nextAction`, and row-level `canRetry`; the UI consumes those fields for Start, Import Results, Retry, Close, Cancel, and Reopen.
- Exposes the existing controlled Cancel Batch and Reopen Payroll services in the production UI. Both reason-required transitions remain server validated; cancellation is limited to Prepared/Exported batches and reopen is limited to Closed batches.
- Fixes stale Payroll Run state after payment processing by invalidating the selected-period payroll context whenever salary-payment state changes, forcing the next Payroll Run view to reload the server status instead of retaining an older Approved snapshot in browser memory.
- Adds service/selector regression coverage for the complete approval and payment chains plus a packaged frontend contract that rejects a return to display-status action inference or loss of lifecycle authority.
- No database migration is required.

# 1.0.54 — Attendance/status contract hardening

- Introduces one backend Payroll attendance contract shared by Internal Attendance and Rental Manpower Timesheets for allowed hours, explicit status codes, text aliases, workflow states, and canonical workflow actions. Blank remains the only incomplete attendance value; numeric 0–24 hours and every supported explicit status are complete values for Submit/Approve/Lock validation.
- Internal Attendance exposes `A` Absent, `L` Leave, `S` Sick, `H` Holiday, and `OFF` through the backend contract. Rental Timesheets expose `A` Absent, `N` No Scope, `L` Leave, and `OFF`. API/import values such as `absent`, `holiday`, `no scope`, `off day`, and `present` normalize at the service boundary instead of relying on browser translation.
- Publishes the authoritative attendance contract in Internal attendance responses and Rental master/timesheet contexts. The browser now normalizes inputs, renders legends/help text, and enables workflow actions from that server contract rather than maintaining separate hard-coded code lists.
- Makes Internal and Rental workflow action aliases converge on `submit`, `approve`, `lock`, and `return_to_draft`; `submit_for_review`, `return`, and `reject` remain accepted service-boundary aliases. Rental revision numbers now advance on Submit, Approve, and Lock as well as correction returns so downstream settlement snapshots have a precise source revision.
- Corrects the Rental bulk controls so `A` is Absent and numeric `0` is Zero hours, and exposes Leave/Off bulk actions. Valid alphabetic attendance statuses no longer appear as invalid merely because they are letters; unsupported text still fails with a controlled validation message.
- Extends DEMO Internal attendance so the seeded grid includes Holiday in addition to Absent, Sick, Leave, Off, and worked-hour rows. Existing Rental DEMO data already covers Absent, No Scope, Leave, Off, and worked-hour rows.
- Adds shared-contract, Internal alias/submission, Rental alias/reject/revision, seed, and packaged frontend authority regression guards. No database migration is required.

# 1.0.53 — Server-side Payroll directory authority

- Moves the six Payroll master registers—Branches / Offices, Departments, Internal Employees, Rental Projects, Manpower Suppliers, and Rental Workforce—onto company-scoped backend search/filter/sort/pagination APIs instead of filtering the visible register from browser master arrays.
- Adds reusable browser directory loading with stale-response protection, loading/error/retry states, backend result counts, Previous/Next navigation, and 25/50/100 row page sizes while preserving existing profile/action navigation.
- Extends Internal organization endpoints with server-derived employee counts and employee-count sorting. Employee list responses now carry selected-period payment-profile/WPS state so WPS filters and row badges use the same backend authority.
- Extends Rental directory APIs with project↔supplier filters, payment-term/workforce/outstanding supplier filters, project client/manager filters, and worker operational-status/project/trade/rate-type filters. Project and supplier rows retain the 1.0.51 settlement financial authority for the selected period.
- Stops embedding the duplicate all-employee organization-history map in the Payroll shell; organization history is loaded with the selected employee profile. Register mutations invalidate the affected server directory so create/edit/lifecycle/transfer/restore actions do not leave stale pages.
- Adds Internal and Rental API regression coverage plus a packaged release contract that rejects removal of server directory pagination or a return to client-side register filtering.
- The shell still retains compact master/reference data used by cross-workspace summaries and workflow pickers; the register rows themselves are server-paginated. Shell-wide reference-cache sizing remains part of the final performance/freeze pass rather than being coupled to this functional cutover.
- No database migration is required.

# 1.0.52 — Internal employee profile backend authority

- Replaces the Internal Employee profile's browser placeholders for overtime, Payroll History, and Recent Activity with a dedicated company-scoped backend profile endpoint.
- Current-period attendance/OT now reads persisted Attendance entries and overtime snapshots; the browser keeps live attendance as a temporary fallback only until the authoritative profile payload arrives.
- Payroll History now reads immutable `PayrollRunLine` snapshots and exposes the related payment state/reference when a salary-payment row exists, so historical payroll no longer appears empty after real runs.
- Recent Activity now reads append-only Internal Payroll audit events related to the employee, organization/salary changes, adjustments, attendance periods, payroll runs, salary-payment batches/rows, and payment-profile changes instead of manufacturing status messages in the browser.
- Adds mutation-aware profile-cache invalidation after attendance/OT, workflow, payroll, payment, salary, organization, lifecycle, and employee master changes.
- Adds selector/API regression coverage plus a packaged frontend/backend authority contract that rejects the former `otHours: 0`, `payrollHistory: []`, and `activity: []` placeholders.
- No database migration is required.

# 1.0.51 — Rental financial authority

- Replaces Rental Project/Supplier financial zero placeholders with authoritative period aggregates from immutable supplier settlement snapshots and supplier-payment allocations.
- Connects project lists, supplier lists, project profiles, supplier profiles, Rental overview controls, and selected-period refreshes to the same backend financial metrics for regular/OT hours, gross/net cost, advances, paid, processing, and outstanding.
- Preserves current workforce/deployment counts from effective-dated assignments while retaining historical financial scopes after worker transfer or release.
- Separates calculated settlement cost from payable exposure: Draft/Calculated settlements contribute cost, but payable/outstanding/available remain zero until Approved or a later payable state.
- Adds reconciliation regression coverage and a release-time static contract that rejects a return of Rental financial zero placeholders or browser-only cost authority.
- No database migration is required.

# 1.0.50 — Idempotent DEMO history-period selection

- Fixes a second or later `./scripts/deploy-production.sh --seed` run failing with `Unable to find a collision-free DEMO history month before existing non-DEMO employment` after the 1.0.48 workflow-ready lifecycle fixtures had already been created.
- Root cause: `_safe_history_period()` used the latest joining date from **every** `DEMO-*` Internal Employee as the lower bound for the closed historical month. Current-period lifecycle fixtures such as `DEMO-190` / `DEMO-192` intentionally join in the live Draft month, so after a successful seed they made the previous closed month look invalid on the next idempotent run.
- Historical period selection now derives its DEMO lower bound only from the 18 base Internal Payroll seed employees (`DEMO-101…DEMO-118`) that actually participate in the finalized historical payroll. Lifecycle/cascade fixtures remain current-period-only and no longer influence historical-month discovery.
- Keeps the non-DEMO safety boundary intact: the history month still must precede real employee employment and remain free of non-DEMO attendance/payroll rows. This change does not relax production payroll isolation.
- Adds static and Django contract coverage so the broad `DEMO-*` lower-bound query cannot return and the historical cohort remains exactly aligned with `INTERNAL_EMPLOYEES`. No database migration or reseeding cleanup is required.

# 1.0.49 — Payroll Run review UI + calculation-detail integrity

- Fixes the Payroll Run header action group wrapping the final **Approve Payroll** action onto a second desktop row. Wide desktop layouts now keep lifecycle actions together; medium layouts intentionally stack the header before controls become cramped.
- Fixes the Review status card text collapsing word-by-word. The V2 bridge previously applied a three-column grid to a two-child DOM, squeezing the full status copy into a 34px column; the review card now maps to its real `copy + snapshot` structure.
- Converts employee Payroll calculation opening into a true **read-only Payroll Run detail** drawer. The drawer is labeled `Payroll run`, does not expose the generic Quick Add footer, and can no longer leak a stale `Create component` action from Salary Setup.
- Makes the native `hidden` state authoritative for Payroll drawer save/footer controls so author CSS cannot accidentally display hidden actions. This also hardens other readonly Payroll drawers.
- Fixes `Total deductions` in the calculation detail drawer producing `SAR NaN` when server snapshot amounts are serialized as decimal strings. Advance recovery and other deductions are normalized to numbers before summing.
- The detail drawer now explicitly reads the same server-authoritative row used by Payroll Register / Review and shows a compact Basic / Allowances / Overtime / Other Earnings reconciliation strip before the saved salary-component snapshot.
- Adds frontend contract checks for readonly Payroll details, numeric deduction reconciliation and shared snapshot sourcing. No database migration is required.

# 1.0.48 — Workflow-ready Internal + Rental current-period seed

- Fixes the seeded September Internal Attendance period being blocked at **Submit for Review** by 36 genuinely missing rows. The status letters were not the problem: `A`, `L`, `S`, `H` and `OFF` are valid explicit attendance values. The missing rows came from lifecycle fixtures created after the original 18-employee attendance grid (`DEMO-190` added 30 required days and `DEMO-192` added 6 employed days).
- The DEMO seed now performs a final current-period readiness pass after lifecycle fixtures. It fills **only missing** required cells, preserves tester-entered attendance, validates the Draft with the same production submission authority, and provisions the current lifecycle employees with salary structures and verified synthetic WPS destinations so later Payroll Run / WPS testing is not blocked.
- Repairs lifecycle fixtures created by 1.0.47 and earlier so `DEMO-190` / `DEMO-192` are current-period fixtures instead of retroactively entering already-finalized DEMO history. Fresh fixtures now start in the live Draft month.
- Rental Manpower was already seeded with 30 `RDEMO-001…030` workers on `DEMO-DIRIYA`; the apparent empty state came from the UI defaulting to the newer lifecycle project `DEMO-YARD`. A new project chooser defaults to the usable non-archived project with the largest active rental workforce while preserving a valid user-selected project.
- Completes current Rental Timesheet data **after** transfer/termination lifecycle fixtures are created. Missing assigned days for `RDEMO-090`, `RDEMO-092`, `RDEMO-093` and related current DEMO assignment segments are populated only where blank, so every seeded current DEMO project is ready for Draft → Submitted → Approved → Locked testing.
- Adds a shared Rental Timesheet completeness validator and revalidates at Submit, Approve and Lock. `A` = Absent, `N` = No Scope, `L` = Leave and `OFF` are valid explicit statuses; only missing assigned worker-days block the workflow.
- Corrects the Rental attendance legend (`0` is zero hours, not Absent; `A` is Absent, not Sick absence) and makes both Internal and Rental helper text explicitly distinguish valid status codes from blank/missing cells.
- Adds regression coverage for mixed explicit status-code submission and approval-time Rental completeness revalidation. No database migration is required for this release.

# 1.0.47 — Nullable-safe tenant reconciliation

- Fixed the production reconciliation false positive that reported `rental_manpower.SupplierPayment.retry_of` as a cross-company reference when `retry_of` is legitimately NULL on an original supplier payment.
- Internal Payroll and Rental Manpower reconciliation now validate company ownership only when a nullable company-owned relation is actually populated; real cross-company references are still rejected.
- Added SupplierPayment model validation so an actual retry link must remain inside the same company and supplier and cannot self-reference.
- Added runtime regression coverage around original-payment + retry reconciliation and a packaged static tenant-reconciliation contract.
- No database migration is required for this release.

# 1.0.46 — E2E cascade seed state-refresh fix

- Fixes `./scripts/deploy-production.sh --seed` falsely reporting that the Branch / Office cascade did not place its employee in the same 30-day recovery window after the PostgreSQL lock fix.
- Root cause: the lifecycle service correctly refetches and locks its own parent model instance, then updates that instance during Delete. The seed kept an older caller-held `deleted_branch` object and compared the freshly deleted child against the stale parent's pre-delete `purge_after=None`.
- Refreshes Branch / Office, Department and Manpower Supplier parent fixtures from the database immediately after their real Delete action before verifying the parent/child `deleted_at` and `purge_after` recovery window.
- Keeps the production cascade implementation unchanged; existing service regression tests already assert exact parent/child delete timestamps and 30-day recovery deadlines.
- Adds a static release gate so all three E2E cascade assertions must refresh their parent record before comparing recovery-window state. No schema or migration change is required.

# 1.0.45 — PostgreSQL cascade-lock compatibility

- Fixes `./scripts/deploy-production.sh --seed` failing during the Branch / Office lifecycle fixture with PostgreSQL `FOR UPDATE is not allowed with DISTINCT clause`.
- Root cause: Branch and Department 30-day cascade Delete locked `InternalEmployee` rows through a reverse organization-assignment join and then called `.distinct()`. PostgreSQL rejects `SELECT DISTINCT ... FOR UPDATE`, even though the cascade itself is valid.
- Keeps row-level locking and the 30-day recoverable cascade semantics intact. The service now resolves current employee ids through `EmployeeOrganizationAssignment` first, then locks the unique `InternalEmployee` rows with `SELECT ... FOR UPDATE` on the outer employee query, with deterministic primary-key ordering.
- Applies the same correction to both Branch / Office and Department Delete so the same production-only failure cannot appear later in the seed or normal lifecycle UI.
- Adds a release gate that rejects any future reintroduction of `DISTINCT` into these PostgreSQL row-locking cascade functions. No schema or migration change is required.

# 1.0.44 — Payroll E2E seed payment chronology fix

- Fixes `./scripts/deploy-production.sh --seed` failing while creating the closed Rental Payroll history with `Payment date cannot be earlier than the settlement approval date`.
- Root cause: the DEMO history is intentionally seeded for the prior closed month, while the real settlement approval transition happens at seed runtime. The fixture incorrectly forced the supplier payment date to that prior month-end, violating the production chronology guard.
- Keeps the production payment rule unchanged. Seeded Paid supplier payments now use the later of the historical period end and the actual settlement approval date, while still rejecting future Paid dates.
- Adds regression coverage for both chronology cases and keeps supplier-payment reports/documents attached to the historical settlement period through their allocation relationship.

# 1.0.43 — Working Actions + recoverable cascade delete + E2E seed verification

- Fixes the Payroll **Actions** dropdown regression on Branch / Office, Department and other lifecycle menus. The delegated controller correctly toggled the dropdown host, but a global CSS hardening rule still disabled pointer events on the menu itself; the open host now explicitly owns menu interactivity and the 1.0.43 assets are cache-busted.
- Adds explicit 30-day cascade-recovery ownership with `core.TrashCascadeLink`. Parent Delete now soft-deletes the exact operational child masters in the same recovery window and parent Restore atomically restores only those children. Independently deleted children are never resurrected by a parent restore.
- Branch / Office and Department Delete now soft-delete their current Internal Employee masters; Manpower Supplier Delete soft-deletes its Rental Worker masters; Project Delete soft-deletes its project Inventory Location and Stock Item masters. Effective-dated assignments, finalized payroll, attendance, settlements, stock movements, generated documents and audit evidence remain protected historical records.
- De-duplicates cascade-owned employees/workers from the Payroll Delete recovery page so users restore the parent boundary once instead of restoring children independently. Inventory Trash similarly hides project-owned cascade children and restores a deleted Project through the project service so its inventory scope is recovered atomically.
- Extends `--seed` lifecycle fixtures to execute real Branch, Department and Supplier cascades and verify child recovery deadlines. The full test seed now fails unless all Payroll report/WPS paths return data and every generated Payroll document type exists for the finalized DEMO history period.
- Adds regression coverage for the parent/child delete window and project inventory cascade, updates retention authority/verification, and adds forward migration `core.0005_trash_cascade_link` without rewriting released migrations.
- Hardens recovery ownership against stale-link edge cases: independently restoring a cascaded child releases the old parent ownership immediately, parent restore requires the original delete/purge window, and expired children retire cascade ownership before purge/tombstone retention. A later independent child delete can therefore never be resurrected or hidden by an older parent delete.

# 1.0.42 — Complete DEMO testing + stop/termination lifecycle

- Expands `--seed` into an idempotent end-to-end Payroll test dataset instead of only sample master rows. The seed now verifies Internal Payroll, Rental Manpower, management workforce cost, overtime, advances/adjustments, payments, transfers and WPS report output.
- Creates a collision-safe closed DEMO history month so approval, locked attendance/timesheets, payroll calculation, supplier settlements, payment workflows and finalized output documents can be exercised without mixing non-DEMO employees into the synthetic finalized payroll.
- Exercises the full Internal salary-payment/WPS lifecycle: company payment settings, verified employee payment destinations, configurable WPS CSV template, batch preparation, export, processing, result import, Paid reconciliation, close, salary slips and salary-payment receipts.
- Exercises Rental settlement output end to end: timesheet + overtime, approved adjustment, calculated/reviewed/approved settlement, paid supplier payment, supplier invoice, settlement document, payment receipt and closed settlement.
- Seeds deterministic lifecycle records for Active, On Leave, temporary Stop, Terminated, Archived and 30-day Delete states, together with transfer/rate-change, On Hold and Completed project scenarios.
- Adds explicit temporary **Stop activity** versus final **Termination** semantics for Internal Employees, Rental Workers and Manpower Suppliers. Temporary stop can be resumed and keeps history; termination is final for that employment/worker/supplier relationship and blocks new operational activity while retaining historical payroll, assignments, timesheets, settlements, payments and documents.
- Supplier termination cascades termination through its current worker scope and safely closes/cancels editable assignment activity where possible. Protected submitted/approved/locked history is retained rather than rewritten.
- Makes rental timesheet lifecycle checks effective-date aware so historical draft corrections through a stop/termination date remain possible while new activity after that date is blocked.
- Adds `rental_manpower.0008_supplier_worker_termination` for supplier stop metadata plus supplier/worker termination dates/reasons and terminated status constraints; no previously released migration is rewritten.
- Updates Supplier and Rental Workforce filters/profile actions for Terminated state and keeps termination out of ordinary master Edit flows. New Internal Employees are no longer created directly as Terminated; termination is an explicit lifecycle action.
- Adds release verification for comprehensive DEMO coverage and stop/termination authority, and bumps Payroll frontend assets to `1.0.42`.

# 1.0.41 — Reversible lifecycle cascade

- Makes Archive and 30-day Delete intentionally less restrictive for the operational masters requested: Branch / Office, Department, Internal Employee, Manpower Supplier, Rental Worker and shared Project.
- Branch / Office and Department lifecycle now cascades operational visibility to employees through the existing current effective-dated organization assignment. Employee rows, employment status and payroll history are not rewritten. Restoring the parent immediately restores only the inherited employee scope.
- Internal employee and rental worker register filters now treat inherited parent lifecycle as a real cascade: ordinary lists exclude children whose current Branch / Department / Supplier is archived or deleted, while Archive/Delete views can surface that inherited state without rewriting the child master.
- Manpower Supplier Archive/Delete now cascades to its worker operational scope without rewriting worker status or assignment history. Workers whose supplier is archived/deleted are rejected from new assignments, timesheet edits and new settlement adjustments until the supplier is restored.
- Individual Internal Employees and Rental Workers may now be archived or soft-deleted while Active; Archive/Delete no longer forces a separate stop/inactive transition. Their historical payroll/assignment records remain intact.
- Project Archive/Delete no longer requires zero stock or released Rental Manpower assignments. Existing project inventory and rental assignment scope becomes non-operational with the project and returns on restore. Project completion remains strict and still requires stock/assignment closeout.
- Adds `Project.archive_previous_status` so project Archive/Restore returns to the exact prior Active / On Hold / Completed state instead of guessing a safe status.
- Adds forward migrations `internal_payroll.0012_reversible_archive_lifecycle` and `projects.0006_project_reversible_archive_state`; no previously released migration is rewritten.
- Keeps Delete recoverable for 30 days and deliberately avoids destructive database cascade. Protected payroll, attendance, assignment, settlement, inventory movement, finalized-document and audit evidence can never be erased merely because a parent master was deleted.
- Updates Archive/Delete screens and Actions hints to describe the reversible cascade and removes old dependency-clearance guidance.

# 1.0.40 — Organization Actions dropdown visibility + lifecycle label cleanup

- Fixes the Branch / Office and Department directory **Actions** control that appeared unresponsive even though the delegated click handler was running: the dropdown was opening inside a generic payroll panel with `overflow: hidden`, so the entire menu was clipped.
- Makes organization-master detail cards allow lifecycle overlays and opens their footer Actions menu upward, while keeping profile/header Actions menus in their existing placement.
- Keeps the shared delegated dropdown controller and server-authoritative lifecycle handlers unchanged; this is a presentation/interaction repair rather than a lifecycle-rule change.
- Renames the Payroll lifecycle navigation from **Archive Bin** to **Archive** and from **Trash Bin** to **Delete**.
- Cleans the visible lifecycle copy so Delete is described as a **30-day recovery** operation instead of exposing the internal Trash/Bin terminology.
- Archive and Delete remain separate operations. Deleted employee, branch/office, department, supplier, worker and project masters remain recoverable for 30 days; protected payroll, assignment, inventory and audit history is still retained.
- Bumps Payroll frontend cache-busters to `1.0.40` so the repaired CSS/JS cannot be masked by a cached 1.0.39 asset.

# 1.0.39 — Record lifecycle actions, 30-day Trash, and SESCCO MS shell branding

- Fixes the dynamically rendered Payroll **Actions** dropdown by moving dropdown open/close behavior to a delegated document-level handler; profile Actions controls now work after route rendering and re-rendering.
- Separates **Archive** and **Delete** as explicit Actions-menu operations instead of mixing them into edit/employment/status forms.
- Adds 30-day soft-delete Trash retention to Internal Employees, Branches / Offices, Departments, Manpower Suppliers and Rental Workers; shared Projects continue on the same 30-day Trash contract.
- Adds dedicated **Archive Bin** and **Trash Bin** Payroll routes with restore actions for Internal Company and Rental Manpower records.
- Delete now means **Move to Trash**. Records are hidden from active selectors immediately, remain recoverable for 30 days, and keep the deletion actor/reason/purge deadline for auditability.
- Keeps historical payroll, attendance, organization assignments, rental assignments, settlements, payments, inventory and audit evidence intact while a master is archived or in Trash.
- Hardens Trash expiry: a physical delete is allowed only when Django's deletion collector proves that no related row would be cascaded or protected; otherwise the expired item becomes a hidden historical tombstone instead of deleting history.
- Adds restore-from-Trash backend actions and audit events for employee, branch/office, department, supplier, worker and project masters.
- Adds forward migrations `internal_payroll.0011_master_trash_retention` and `rental_manpower.0007_master_trash_retention`; no previously released migration is rewritten.
- Locks the product shell identity to **SESCCO MS — Management System** so an environment override cannot restore the old “Project Inventory” brand label.
- Extends production lifecycle verification and frozen migration/source manifests for the new retention contract.

# 1.0.38 — Immutable branding-migration lineage repair

- Repairs the production failure `column core_company_settings.document_branding_mode does not exist` seen after migrations completed and the `--seed` phase started.
- Restores `core.0003_company_document_branding` to the exact migration that originally shipped and may already be recorded as applied in production; previously released migrations are no longer rewritten.
- Adds forward-only `core.0004_company_document_branding_lineage_repair`, which idempotently adds the missing branding-mode database column when needed and safely accepts databases where it already exists.
- Reconciles both known database lineages by preserving/widening branding file columns to 180 characters, enough for SESCCO branding storage keys.
- Restores the 12 MB branding upload-size validator while keeping the current logo / letterhead / watermark storage layout and extension checks.
- The repair preserves existing company settings and existing branding file references; it does not delete or rewrite uploaded branding assets.
- Adds a frozen migration-lineage verifier so an already-released migration cannot be silently edited again.
- Adds a post-migration physical-schema gate before `--seed`, so migration-recorder/schema divergence fails with a direct release error instead of an ORM traceback.

# 1.0.37 — Branding migration-state repair

- Fixes the production pre-deployment `makemigrations --check --dry-run` failure introduced by a serialization-shape mismatch in the company document-branding file-extension validator.
- Makes the live `CompanySettings` model use the same keyword-form `FileExtensionValidator(allowed_extensions=...)` constructor already frozen in migration `core.0003_company_document_branding`.
- Prevents Django from proposing the schema-no-op `0004_alter_companysettings_document_letterhead_and_more` migration for logo, letterhead and watermark fields.
- Does not add or apply a new database migration and does not modify existing company branding data.
- The `security.W021` HSTS preload message remains a non-blocking deployment warning; this patch does not opt the domain into browser preload policy automatically.

# 1.0.36 — Lifecycle retention governance

- Adds a machine-readable lifecycle/retention contract covering all 58 persisted SESCCO MS models so every new model must declare how it may leave active use.
- Freezes the rule that real master data uses Archive / Restore / guarded Delete-unused while operational history uses workflow states, effective dating, reversal or immutability instead of generic destructive actions.
- Explicitly classifies system users and memberships as deactivate/reactivate-only, company/settings/policies as retained singletons, and saved views/preferences as ordinary user-owned disposable data.
- Keeps Internal Payroll salary structures effective-dated and changes the UI action from misleading “Edit” to “Create effective change”; historical structures are retained rather than archived or deleted.
- Clarifies that the company payroll proration policy is retained singleton configuration and that changing it only affects future calculations.
- Adds `verify-lifecycle-retention-contract.py` to the production-freeze gate; it fails if a persisted SESCCO model is added without a retention classification or if key lifecycle safeguards regress.
- Adds `docs/LIFECYCLE_RETENTION.md` and `merge/lifecycle-retention-contract.json` as the operator/developer authority for Archive, Delete-unused, effective-dated, workflow and immutable record behavior.
- No historical payroll, attendance, rental, inventory, audit or finalized document data is rewritten or removed by this upgrade.

# 1.0.35 — Unified lifecycle UX

- Converged Internal Payroll, Rental Manpower, Projects and Inventory master records onto one consistent Actions-menu pattern for edit, lifecycle, archive/restore and guarded delete-unused operations.
- Added shared Payroll lifecycle menu/panel/error styling plus shared Inventory/Project lifecycle-action styling, with destructive delete actions visually separated from archive/restore.
- Lifecycle drawers now explain archive versus permanent delete and show backend dependency blockers inline instead of relying on transient toast messages alone.
- Fixed the Payroll drawer save gate so organization, rental-master and configuration lifecycle actions are accepted by the shared save path.
- Kept lifecycle enforcement server-authoritative: archive preserves real history; permanent deletion remains available only for unused records that pass dependency checks.

# 1.0.34 — Secondary configuration lifecycle

- Added lifecycle authority for Internal Payroll salary components, overtime policies and bank/WPS export templates.
- Added Archive / Restore-as-Inactive / Delete-unused actions with required archive reasons, typed delete confirmation and append-only audit events.
- Protected historical salary structures, overtime references and salary-payment batches from destructive master-data deletion.
- Archived salary components, overtime policies and export templates are excluded from new salary structures, OT assignments and payment batches while historical snapshots remain readable.
- Added guarded Delete-unused for employee payment profiles; profiles with salary-payment history must be made Inactive instead.
- Kept company salary-payment settings permanent and kept system users on the existing deactivate/reactivate-only policy so audit actor history is retained.
- Added Archived filtering and lifecycle controls in Salary Setup and Bank/WPS template UI, plus release verification and migration `0010_secondary_configuration_lifecycle`.

# 1.0.33 — Projects + Inventory master lifecycle

- Applies the central lifecycle authority to shared Projects and Inventory Units, Material Suppliers, Stock Records and Office Inventory Locations.
- Separates Archive from 30-day Trash: Archive preserves valid historical masters, while Trash is limited to unused records created by mistake.
- Blocks project archive while positive stock or open/future Rental Manpower assignments remain, and blocks Delete-unused after Inventory or Rental history exists.
- Keeps archived masters resolvable in historical Inventory/Payroll records while excluding them from new operational selectors.
- Synchronizes each project-owned Inventory Location to the shared Project lifecycle instead of allowing a second conflicting lifecycle.
- Prevents stock transfers from silently reactivating archived destination stock and requires an explicit Restore.
- Prevents archived material suppliers and units from being reused in new stock activity until explicitly restored.
- Adds lifecycle-safe Office Inventory support for multiple SESCCO branches/offices and a dedicated Inventory Locations workspace.
- Extends Trash, Archive, audit, release verification and frozen migration manifests for the new master-data lifecycle.

# 1.0.32 — Rental Manpower supplier / worker lifecycle

- Adds central-authority Archive / Restore / Delete-unused lifecycle to Manpower Suppliers and Rental Workers.
- Adds effective worker inactive date/reason and archive metadata without rewriting assignment history.
- Blocks supplier archive/deactivation while active workers remain and blocks hard delete after worker, settlement, adjustment or payment history exists.
- Blocks worker inactivation/archive while current or scheduled assignments remain and blocks hard delete after assignment/timesheet/adjustment/settlement history exists.
- Restored suppliers/workers return as Inactive and must be deliberately reactivated.
- Archived records remain visible for historical profiles but are excluded from new operational supplier/worker selection.
- Adds lifecycle controls and Archived filters to the Rental Manpower UI.

# 1.0.31 — Branch / Office + Department lifecycle

- Adds explicit Branch vs Office classification without splitting organization history.
- Adds Archive / Restore / Delete-unused lifecycle for branches/offices and departments through the central lifecycle authority.
- Blocks archive/deactivation while current employed workers still use the master and blocks hard delete once assignment/payroll history exists.
- Archived masters remain resolvable in historical employee/payroll context but disappear from new-assignment selectors.
- Restored organization masters return as Inactive and must be deliberately reactivated.
- Adds Active / Inactive / Archived / All register filters and lifecycle drawers in Internal Payroll.
- Prevents an inactive employee from returning to payroll eligibility while their current branch/department is archived or inactive.

# 1.0.30 — Central lifecycle authority

- Adds one shared backend lifecycle authority for master-data Archive, Restore, Delete and Deactivate decisions across SESCCO MS.
- Standardizes `can_archive`, `can_restore`, `can_delete`, `delete_blockers`, `can_deactivate` and `archive_reason_required` behind registered module policies instead of page-specific rules.
- Adds structured blocker codes/messages/counts, confirmation-token handling and operation reason requirements while keeping permissions in the owning module services.
- Standardizes lifecycle audit metadata with lifecycle action/policy, reason and dependency counts on the existing immutable `AuditEvent` ledger.
- Migrates the Internal Employee archive/deactivate/restore/delete safeguards onto the central authority as the reference implementation without changing its user-facing lifecycle semantics.
- Exposes employee lifecycle capabilities separately from register serialization so profile/action surfaces can consume authoritative state without introducing N+1 blocker queries on employee lists.
- Adds central lifecycle regression tests and a production-freeze verifier; no database migration or historical-data rewrite is required.

# 1.0.29 — SESCCO MS single-company foundation

- Rebrands the private deployment as **SESCCO MS — Management System** using the supplied SESCCO mark across Inventory, Payroll, authentication and error surfaces.
- Introduces explicit single-company mode while preserving the existing company foreign-key/security boundary internally.
- Removes the production company switcher from the shell and keeps only authorized module/workspace switching.
- Adds production checks for exactly one active company and optional primary-company slug pinning.
- Rewords platform navigation from SaaS-oriented “business area” terminology to private-system “module” terminology.

# SESCCO IMS 1.0.28

- Adds a production employee-employment lifecycle to Internal Payroll instead of treating status as a normal editable profile field.
- Adds explicit Active, On Leave, Inactive and Terminated transitions with audited reasons; termination requires an employment end date and closes the open branch/department assignment at that date.
- Adds Archive / Restore Archive for stopped employee masters. Archived records are removed from the default current-employee register but remain available through the Archived filter with all historical payroll, attendance, payment and document references retained.
- Adds guarded hard deletion for unused/duplicate onboarding masters only. The operator must type the employee ID, and any attendance, overtime, adjustment, payroll-run, salary-payment or finalized salary-slip history blocks deletion and directs the operator to Archive instead.
- Removes protected employment status/end-date editing from the ordinary Edit Employee drawer and adds a dedicated Employment action with lifecycle guidance.
- Adds lifecycle banners and status visibility on the employee profile, disables organization reassignment while an employee is inactive/terminated/archived, and preserves effective-dated organization history.
- Fixes the Internal Employee profile header spacing at the final Payroll CSS authority layer so the old unlayered `.entity-header` rule can no longer collapse horizontal padding.
- Adds API/service regression coverage for termination, archive filtering, leave audit requirements and guarded unused-master deletion.
- Adds a release-time employee-lifecycle verifier and freezes the new lifecycle migration in the production migration/source manifests.
- No historical payroll, attendance, payment or finalized document snapshot is deleted or rewritten by deactivation, termination or archive.

# SESCCO IMS 1.0.27

- Completes Payroll reference-output parity for salary slips and employee payment documents.
- Adds salary amount in words, paid-by/payment reference presentation and employee/manager signature areas to finalized salary-slip output.
- Adds private company logo, A4 letterhead and watermark assets to Payroll document settings and snapshots branding identity for immutable finalized documents.
- Preserves company legal identity, CR, VAT, address, email, phone and website on generated Payroll/Manpower documents.
- Extends seeded Payroll test data with safe synthetic document-branding fixtures and corresponding release verification.

# SESCCO IMS 1.0.26

- Converts the supplied company payroll reference documents into explicit production contracts instead of leaving them as spreadsheet-only knowledge.
- Extends Internal Employee masters with a managed address field and carries the address into immutable salary-payment snapshots, search, API payloads and WPS readiness.
- Expands configurable Bank/WPS templates so bank-owned layouts may omit the internal employee number when the external contract identifies rows by bank account / Iqama; Net Salary remains mandatory.
- Adds the source-compatible WPS column shape: Bank, Account Number, Total Salary, Transaction Reference, Employee Name, National ID/Iqama ID, Employee Address, Basic Salary, Housing Allowance, Other Earnings and Deductions.
- Adds company print identity settings for Commercial Registration, VAT number, document address/email/phone and website, and snapshots them into finalized payroll/manpower documents.
- Upgrades finalized salary slips to render component-level earnings/deductions, employee Iqama/address and the existing immutable payroll snapshot rather than relying on a fixed four-line earnings layout.
- Adds an idempotent `seed_payroll_test_data` management command and wires `scripts/deploy-production.sh --seed` / `scripts/deploy-production-freeze.sh --seed` through the normal post-migration release runner.
- The seed creates 18 DEMO internal employees and 30 RDEMO rental workers, organization masters, salary components, Basic/300 × OT × 1.5 test overtime policy, payment/WPS profiles, supplier/project/assignments, attendance/timesheets, adjustments and a current draft test period.
- On a clean/demo tenant, the seed also builds a previous-month closed lifecycle covering approved payroll, WPS payment reconciliation, salary slips/receipts, locked rental timesheet, supplier settlement/invoice/payment/receipt and closed settlement history.
- Seeded bank accounts, Iqama/IDs, phone numbers and references are synthetic DEMO data; uploaded production bank/identity values are not copied into source code or fixtures.
- Adds regression coverage for company document identity settings, the source-compatible WPS layout without an internal employee-number column, synthetic Saudi IBAN generation, and Internal/Rental seed population counts.
- Adds a release-time `verify-payroll-reference-coverage.py` gate and includes it in the production-freeze verifier.
- No real payroll history is auto-approved by the seed: closed-history generation is skipped when non-DEMO Internal or Rental worker masters already exist.

# SESCCO IMS 1.0.25

- Fixes the Internal Payroll card-height regression visible on Salary Payments and Bank & WPS Export.
- Reduces the no-payment-batch empty state from the old 300px prototype minimum to a compact 116px production state, while preserving the same message, icon and Bank/WPS action.
- Fixes the oversized Bank/WPS `Export template` launcher at its actual source: `.bank-template-picker` was incorrectly normalized as a row toolbar, so the shared `flex-basis: 220px` became vertical height inside its column layout.
- Removes `.bank-template-picker` from row-toolbar normalization and normalizes only its native select. The picker now uses an explicit two-row label/control grid with a 42px launcher and no vertical flex sizing.
- Cleans both duplicated Internal Payroll V2 payment-empty rules (`pages/payroll.css` and the PRS execution cutover) so an older imported rule cannot restore the 300px height later in the cascade.
- Keeps the final Payroll control stylesheet as the single authority for operational select geometry; no new broad `!important` card-height patch was added.
- Extends release verification to reject putting the Bank/WPS template picker back into the generic toolbar selector and to enforce the compact Internal Payments empty-state height.
- Updates the final Payroll control asset cache-buster to `1.0.25`.
- No payroll calculations, attendance logic, salary-payment workflow, Bank/WPS data generation, APIs, database schema, permissions, authorization or tenant isolation are changed.
