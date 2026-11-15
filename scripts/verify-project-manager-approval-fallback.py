#!/usr/bin/env python3
"""Offline source guard for manager-backed inventory stock approvals.

Production decision behavior remains covered by Django/PostgreSQL tests in
apps.inventory.tests.test_project_stock_approvals.
"""
from pathlib import Path
import ast
ROOT = Path(__file__).resolve().parents[1]
checks = {
    'apps/inventory/services/approvals.py': [
        '_eligible_project_approvers', 'can_decide', 'inventory_manager_id',
        'PulseProjectTeamMember', 'role-project-manager',
        'membership_allows_project', 'INVENTORY_STOCK_APPROVE',
        'req.requested_by_id == user.pk', 'if row.status != StockApprovalDecision.Status.APPROVED',
    ],
    'apps/inventory/views.py': [
        'def _visible_stock_approvals', 'StockApprovalDecision.objects.filter',
        'if can_decide(request.user, project)',
    ],
    'apps/inventory/tests/test_project_stock_approvals.py': [
        'test_fallback_to_scoped_project_manager_with_no_inventory_assignee',
        'test_no_eligible_project_manager_blocks_before_stock_posting',
        'test_dedicated_inventory_approver_overrides_all_scoped_project_manager',
        'test_pulse_project_manager_can_approve_when_explicit_inventory_assignee_empty',
        'test_revoking_pulse_manager_approval_fails_closed',
        'test_all_scoped_project_manager_can_approve_new_company_project',
        'test_manager_cannot_approve_own_submission',
    ],
}
for rel, needles in checks.items():
    text = (ROOT / rel).read_text(encoding='utf-8')
    ast.parse(text, rel)
    for needle in needles:
        if needle not in text:
            raise SystemExit(f'MANAGER APPROVAL CHECK FAILED: {rel} missing {needle}')
print('Project manager inventory approval source guards passed; run Django regression tests on staging.')
