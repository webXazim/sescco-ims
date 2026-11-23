#!/usr/bin/env python3
"""Offline source guard for permission-based inventory stock approvals.

Production decision behavior remains covered by Django/PostgreSQL tests in
apps.inventory.tests.test_project_stock_approvals.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks = {
    'apps/inventory/services/approvals.py': [
        '_eligible_project_approvers', 'can_decide', 'can_decide_request',
        '_valid_approver_membership',
        'membership_allows_project', 'INVENTORY_STOCK_APPROVE',
        '_require_projects', '_is_company_owner', '_required_decisions', 'is_required=True',
        'if row.status != StockApprovalDecision.Status.APPROVED',
    ],
    'apps/inventory/services/transfers.py': [
        'if destination_location.project_id and approved_request is None',
        'project_ids=[destination_location.project_id]',
    ],
    'apps/inventory/views.py': [
        'def _visible_stock_approvals', 'InventoryApprovalAccessMixin',
        'StockApprovalDecision.objects.filter',
        'if can_decide(request.user, project)',
    ],
    'apps/inventory/tests/test_project_stock_approvals.py': [
        'test_custom_profile_approves_without_manager_designation',
        'test_custom_permission_revocation_stops_approval',
        'test_permission_only_user_can_view_review_and_decide',
        'test_receive_only_can_submit_and_see_own_request',
        'test_transfers_require_destination_project_decision',
        'test_manager_cannot_approve_own_submission',
        'test_company_owner_can_submit_and_approve_destination_transfer_with_activity',
    ],
}
for rel, needles in checks.items():
    text = (ROOT / rel).read_text(encoding='utf-8')
    ast.parse(text, rel)
    for needle in needles:
        if needle not in text:
            raise SystemExit(f'MANAGER APPROVAL CHECK FAILED: {rel} missing {needle}')
print(
    'Permission-based inventory approval source guards passed; '
    'run Django regression tests on staging.'
)

# Role names and project manager designation must not gate a profile grant.
approval_source = (ROOT / 'apps/inventory/services/approvals.py').read_text(encoding='utf-8')
module = ast.parse(approval_source)
methods = {
    node.name: ast.get_source_segment(approval_source, node)
    for node in module.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
}
resolver = methods['_eligible_project_approvers']
if 'role-project-manager' in resolver or 'inventory_manager_id' in resolver:
    raise SystemExit('PERMISSION APPROVAL CHECK FAILED: resolver restricts custom-profile grants')
if 'permission_grants__permission=' not in resolver:
    raise SystemExit('PERMISSION APPROVAL CHECK FAILED: resolver not based on stored grant')
if '_eligible_project_approvers(' in methods['can_decide']:
    raise SystemExit(
        'PERMISSION APPROVAL CHECK FAILED: can_decide still requires a designated manager'
    )
if '_require_projects(company, project_ids)' not in methods['queue_request']:
    raise SystemExit(
        'PERMISSION APPROVAL CHECK FAILED: request submission still requires a manager'
    )
for label in ('StockApprovalListView', 'StockApprovalDetailView', 'StockApprovalAttachmentView'):
    views_source = (ROOT / 'apps/inventory/views.py').read_text(encoding='utf-8')
    if f'class {label}(InventoryApprovalAccessMixin' not in views_source:
        raise SystemExit(f'PERMISSION APPROVAL CHECK FAILED: {label} blocks approval-only profiles')
permissions_source = (ROOT / 'apps/accounts/permissions.py').read_text(encoding='utf-8')
if 'AccessPermission.INVENTORY_STOCK_APPROVE}' not in permissions_source:
    raise SystemExit(
        'PERMISSION APPROVAL CHECK FAILED: approval-only users cannot open Inventory workspace'
    )
print(
    'Custom-profile approval, submission separation, and inbox accessibility '
    'source checks passed.'
)
