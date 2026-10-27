"""Allocate internal project routing codes without asking users to provide them.

The human-readable project name is the UI tag. The internal code is kept for
legacy URLs, Inventory/Payroll contracts, and immutable historical links.
"""
from __future__ import annotations

import re
import unicodedata

from .models import Project


def generate_project_code(*, company, name: str) -> str:
    """Return an available company-scoped code from a project name.

    Call inside a transaction holding a row lock on the owning Company so that
    simultaneous project creations cannot choose the same candidate.
    """
    latin = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Z0-9]+", "-", latin.upper()).strip("-")[:30].rstrip("-") or "PROJECT"
    code = stem
    sequence = 2
    while Project.objects.for_company(company).filter(code=code).exists():
        suffix = f"-{sequence}"
        code = stem[: 30 - len(suffix)].rstrip("-") + suffix
        sequence += 1
    return code
