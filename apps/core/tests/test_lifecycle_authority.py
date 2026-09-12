from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.core.models import AuditArea
from apps.core.services.lifecycle import (
    LifecycleAction,
    LifecycleBlocker,
    LifecyclePolicy,
    archive_reason_required,
    can_archive,
    can_deactivate,
    can_delete,
    can_restore,
    delete_blockers,
    lifecycle_capabilities,
    register_lifecycle_policy,
    require_lifecycle_action,
)


@dataclass
class DemoLifecycleRecord:
    code: str = "DEMO-001"
    state: str = "active"
    historical_rows: int = 0


class DemoLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.CORE
    object_type = "core.DemoLifecycleRecord"
    supported_actions = frozenset(
        {
            LifecycleAction.ARCHIVE,
            LifecycleAction.RESTORE,
            LifecycleAction.DELETE,
            LifecycleAction.DEACTIVATE,
        }
    )
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.DEACTIVATE})

    def confirmation_token(self, instance):
        return instance.code

    def dependency_evidence(self, instance, action):
        return {"historical_rows": instance.historical_rows} if action is LifecycleAction.DELETE else {}

    def blockers(self, instance, action, *, evidence):
        if action is LifecycleAction.ARCHIVE and instance.state not in {"inactive", "archived"}:
            return (LifecycleBlocker(code="still_active", field="record", message="Deactivate first."),)
        if action is LifecycleAction.RESTORE and instance.state != "archived":
            return (LifecycleBlocker(code="not_archived", field="record", message="Not archived."),)
        if action is LifecycleAction.DEACTIVATE and instance.state != "active":
            return (LifecycleBlocker(code="not_active", field="record", message="Not active."),)
        if action is LifecycleAction.DELETE and evidence.get("historical_rows", 0):
            return (
                LifecycleBlocker(
                    code="history_exists",
                    field="record",
                    message="History blocks deletion.",
                    count=evidence["historical_rows"],
                ),
            )
        return ()


register_lifecycle_policy(DemoLifecycleRecord, DemoLifecyclePolicy())


class LifecycleAuthorityTests(SimpleTestCase):
    def test_capabilities_are_structural_and_do_not_fail_for_missing_operation_input(self):
        record = DemoLifecycleRecord(state="active")
        self.assertTrue(can_deactivate(record))
        self.assertFalse(can_archive(record))
        self.assertFalse(can_restore(record))
        self.assertTrue(can_delete(record))
        self.assertTrue(archive_reason_required(record))

        capabilities = lifecycle_capabilities(record)
        self.assertTrue(capabilities["canDeactivate"])
        self.assertTrue(capabilities["canDelete"])
        self.assertTrue(capabilities["actions"]["delete"]["confirmationRequired"])
        self.assertEqual(capabilities["actions"]["delete"]["confirmationToken"], "DEMO-001")

    def test_operation_validation_enforces_reason_and_confirmation(self):
        inactive = DemoLifecycleRecord(state="inactive")
        with self.assertRaises(ValidationError):
            require_lifecycle_action(inactive, LifecycleAction.ARCHIVE)
        decision = require_lifecycle_action(inactive, LifecycleAction.ARCHIVE, reason="No longer operational")
        self.assertTrue(decision.allowed)

        active = DemoLifecycleRecord(state="active")
        with self.assertRaises(ValidationError):
            require_lifecycle_action(active, LifecycleAction.DELETE, confirmation="WRONG")
        decision = require_lifecycle_action(active, LifecycleAction.DELETE, confirmation="DEMO-001")
        self.assertTrue(decision.allowed)

    def test_dependency_blockers_are_returned_with_evidence(self):
        record = DemoLifecycleRecord(state="inactive", historical_rows=3)
        self.assertFalse(can_delete(record))
        blockers = delete_blockers(record)
        self.assertEqual(len(blockers), 1)
        self.assertEqual(blockers[0].code, "history_exists")
        self.assertEqual(blockers[0].count, 3)
