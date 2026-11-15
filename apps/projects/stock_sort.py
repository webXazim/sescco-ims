"""Explicit inventory ordering shared by project pages and their CSV/XLSX exports.

Do not accept ORM order_by paths from URL parameters. The allowlist also has
stable tie-breakers so pagination and exports cannot randomly reorder rows.
"""
from django.db.models import F

# Project inventory is a separate page from Inventory Explorer. Apply its own
# explicit ordering *before* pagination; never trust ORM field names from GET.
PROJECT_STOCK_SORTS = {
    "created": ("-created_at", "-pk"),
    "oldest-created": ("created_at", "pk"),
    "updated": ("-updated_at", "-pk"),
    "oldest-updated": ("updated_at", "pk"),
    "material": ("material_name", "supplier_name", "pk"),
    "-material": ("-material_name", "supplier_name", "pk"),
    "quantity": ("current_quantity", "material_name", "pk"),
    "-quantity": ("-current_quantity", "material_name", "pk"),
    "latest-addition": (F("latest_addition_date").desc(nulls_last=True), "-created_at", "-pk"),
    "oldest-addition": (F("latest_addition_date").asc(nulls_last=True), "created_at", "pk"),
}
PROJECT_STOCK_SORT_CHOICES = (
    ("created", "Recently added first"),
    ("oldest-created", "Oldest added first"),
    ("updated", "Recently updated first"),
    ("oldest-updated", "Least recently updated"),
    ("material", "Material name A–Z"),
    ("-material", "Material name Z–A"),
    ("-quantity", "Highest quantity first"),
    ("quantity", "Lowest quantity first"),
    ("latest-addition", "Latest stock receipt first"),
    ("oldest-addition", "Oldest stock receipt first"),
)

