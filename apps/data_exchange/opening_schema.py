OPENING_IMPORT_COLUMNS = (
    {"name": "Project Code", "required": True, "format": "Active project code", "example": "SESCCO-IMS"},
    {"name": "Material Name", "required": True, "format": "Text", "example": "Portland Cement"},
    {"name": "Description", "required": False, "format": "Text", "example": "50 kg bag"},
    {"name": "Supplier Name", "required": True, "format": "Text", "example": "Gulf Cement"},
    {"name": "Supplier Phone", "required": True, "format": "Text; keep + or leading zero", "example": "+966 57 318 0396"},
    {"name": "Supplier Location", "required": False, "format": "Text", "example": "Dammam"},
    {"name": "Unit", "required": True, "format": "Active unit name or symbol", "example": "bag"},
    {"name": "Opening Quantity", "required": True, "format": "Number greater than 0", "example": "125.000"},
    {"name": "Unit Price", "required": False, "format": "Number, 0 or greater", "example": "24.50"},
    {"name": "Opening Date", "required": True, "format": "Date; YYYY-MM-DD recommended", "example": "2026-08-07"},
    {"name": "Minimum Quantity", "required": False, "format": "Number, 0 or greater", "example": "20.000"},
    {"name": "Reference", "required": False, "format": "Text", "example": "OPEN-001"},
    {"name": "Notes", "required": False, "format": "Text", "example": "Verified opening count"},
)

OPENING_IMPORT_RULES = (
    "Use one row for each project, material, supplier and phone identity.",
    "Project Code and Unit must match active values available in the system.",
    "Opening Quantity must be greater than zero and Opening Date cannot be in the future.",
    "Do not repeat the same stock identity in multiple rows.",
    "The importer shows a row-by-row preview before anything is saved.",
)
