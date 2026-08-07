# Upgrade 2 — Projects and stock-record management

This upgrade turns the approved project and inventory prototype screens into persistent Django workflows while deliberately leaving quantity-changing transactions for Upgrade 3.

## Completed

### Projects

- Project model with unique uppercase project codes.
- Active, completed, and archived lifecycle.
- Client, location, schedule, and notes.
- Storekeeper project list, create, edit, and detail screens.
- Project tags used throughout inventory screens.
- Project-level stock counts, low-stock counts, and recent update dates.
- Projects with stock records are protected from physical deletion.
- New stock records are accepted only by active projects.

### Units

- Managed quantity units with normalized unique names and symbols.
- Common construction units seeded by migration.
- Storekeeper unit management screen.
- Inactive units remain attached to existing records but cannot be selected for new stock or unit changes.

### Stock records

- Stock item belongs to one project and one unit.
- Identity is enforced as project + normalized material + normalized supplier + normalized supplier phone.
- Case, extra spaces, phone spaces, punctuation, `+`, and `00` prefixes are normalized.
- Exact duplicates are blocked by form validation and a database unique constraint.
- Similar material/supplier records with a changed phone are surfaced for review.
- Material, supplier, minimum quantity, notes, and lifecycle status can be managed.
- Current quantity, latest price, and latest addition date are read-only metadata reserved for the transaction engine.
- Inventory list, baseline filters, sorting, pagination, stock detail, and low-stock pages are functional.
- Project inventory details paginate without silently truncating large result sets.
- Concurrent duplicate create/update races are converted into safe form errors.
- An authenticated JSON match endpoint is available for Upgrade 3's add-stock form.

### Safety and administration

- Current quantity cannot be edited from custom forms or Django admin.
- Non-negative database constraints protect current and minimum quantities.
- Project, unit, and stock records are protected from destructive admin deletion.
- Created/updated user attribution is recorded.
- Django admin has search, filters, autocomplete, and read-only system fields.

## Not included yet

Upgrade 3 will add immutable stock movements, stock addition, stock usage, adjustments, reversals, concurrency locks, negative-stock protection, and duplicate-submit protection.

Upgrade 5 will replace the baseline inventory filters with the full date presets, advanced filter builder, saved views, and exact-result export workflow.
