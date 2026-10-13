#!/usr/bin/env python3
"""Static source contract only; does not replace Django migration / HTTP tests."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    if path.endswith(".py"):
        ast.parse(text, filename=path)
    return text


def require(file, *tokens):
    text = source(file)
    for token in tokens:
        assert token in text, f"missing {token!r} in {file}"


require("apps/sourcing/models/subcontractors.py", "class SourcingSubcontractorVerificationRevision", "on_delete=models.SET_NULL", "objects = ImmutableSourcingRevisionManager()", "subcontractor_id_snapshot")
require("apps/sourcing/migrations/0011_subcontractor_company_verification.py", "clear_ambiguous_profile_freshness", "SourcingSubcontractorVerificationRevision", "RunPython")
require("apps/sourcing/services/subcontractor_verification.py", "@transaction.atomic", "def verify_subcontractor", "sourcing.subcontractor.company_verified", "SourcingSubcontractorVerificationRevision.objects.create")
require("apps/sourcing/services/subcontractors.py", "obj.last_verified_at = None", "SourcingSubcontractorVerificationRevision._base_manager.filter(")
assert "_touch_subcontractor" not in source("apps/sourcing/services/subcontractor_catalog.py"), "Service verification must not mark company details verified."
require("apps/sourcing/selectors/subcontractors.py", "subcontractor_verification_page", ".for_company(company)", "stamp_subcontractor_freshness")
require("apps/sourcing/urls.py", 'name="subcontractor_verify"', 'name="subcontractor_verification_history"')
require("apps/sourcing/views.py", "def subcontractor_verify(", "def subcontractor_verification_history(", "_require_subcontractor_view(request)", "_require_subcontractor_manage(request)")
for rel in ("templates/sourcing/subcontractors/verify.html", "templates/sourcing/subcontractors/verification_history.html"):
    require(rel, "{% csrf_token %}" if rel.endswith("verify.html") else "{% for revision in entries %}")
require("apps/sourcing/tests/test_subcontractor_verification.py", "def test_company_verification_independent_of_service_offer_confirmation", "def test_permanent_delete_retains_detached_verification_snapshots", "def test_permission_boundaries_and_other_company_404")
require("merge/lifecycle-retention-contract.json", '"sourcing.SourcingSubcontractorVerificationRevision"', '"mode": "immutable_reference_history"')
print("PASS: Upgrade 06 source-level verification and independent freshness contract (Django runtime not executed).")
