"""Machine-readable Sourcing boundary contract.

Sourcing records answer only "who can we call and what did they say they can
provide?" They never create or mutate stock, operational suppliers, workers,
assignments, payroll, payments, accounting postings or project activity.
"""

FORBIDDEN_OPERATIONAL_APP_LABELS = frozenset({
    "inventory",
    "projects",
    "internal_payroll",
    "rental_manpower",
    "documents",
    "data_exchange",
})

FORBIDDEN_OPERATIONAL_MODEL_NAMES = frozenset({
    "Supplier",
    "StockItem",
    "StockMovement",
    "ManpowerSupplier",
    "RentalWorker",
    "WorkerAssignment",
})
