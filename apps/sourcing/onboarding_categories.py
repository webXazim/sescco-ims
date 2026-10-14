"""Categories staged while a new sourcing provider and its capabilities are unsaved.

A category is not a separate table row: it becomes a company vocabulary value
only after its first Material/Service master is committed. Include active sibling
master drafts in the current request's form choices, without writing ahead of the
atomic provider transaction or reading another tenant's records.
"""
from __future__ import annotations

from .models.base import clean_text


def pending_master_categories(post, *, category_field: str, new_category_field: str,
                              name_field: str, prefix: str = "supply_items") -> list[str]:
    if not post or not all((category_field, new_category_field, name_field)):
        return []
    try:
        total = min(100, max(0, int(post.get(f"{prefix}-TOTAL_FORMS", "0"))))
    except (ValueError, TypeError):
        return []
    found, seen = [], set()
    for index in range(total):
        key = f"{prefix}-{index}-"
        if str(post.get(key + "DELETE", "")).lower() in ("on", "true", "1", "yes"):
            continue
        if not clean_text(post.get(key + name_field, "")):
            continue
        if post.get(key + category_field) != "__new__":
            continue
        category = clean_text(post.get(key + new_category_field, ""))
        if not category or len(category) > 120:
            continue
        folded = category.casefold()
        if folded not in seen:
            seen.add(folded)
            found.append(category)
    return found
