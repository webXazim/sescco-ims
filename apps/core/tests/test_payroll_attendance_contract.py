from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.core.payroll_attendance_contract import (
    ATTENDANCE_WORKSPACE_INTERNAL,
    ATTENDANCE_WORKSPACE_RENTAL,
    attendance_contract_payload,
    normalize_attendance_workflow_action,
    normalize_payroll_attendance_value,
)


class PayrollAttendanceContractTests(SimpleTestCase):
    def test_internal_contract_exposes_all_supported_codes(self):
        contract = attendance_contract_payload(ATTENDANCE_WORKSPACE_INTERNAL)
        self.assertEqual([row["value"] for row in contract["codes"]], ["A", "L", "S", "H", "OFF"])
        self.assertTrue(contract["blankMeansMissing"])
        self.assertTrue(contract["explicitStatusCompletesDay"])

    def test_rental_contract_exposes_all_supported_codes(self):
        contract = attendance_contract_payload(ATTENDANCE_WORKSPACE_RENTAL)
        self.assertEqual([row["value"] for row in contract["codes"]], ["A", "N", "L", "OFF"])

    def test_internal_aliases_and_hours_normalize_at_backend_boundary(self):
        self.assertEqual(
            normalize_payroll_attendance_value("holiday", workspace=ATTENDANCE_WORKSPACE_INTERNAL),
            (0, "H", "H"),
        )
        self.assertEqual(
            normalize_payroll_attendance_value("present", workspace=ATTENDANCE_WORKSPACE_INTERNAL),
            (8, "", "8"),
        )
        self.assertEqual(
            normalize_payroll_attendance_value("7.555", workspace=ATTENDANCE_WORKSPACE_INTERNAL),
            (normalize_payroll_attendance_value("7.56", workspace=ATTENDANCE_WORKSPACE_INTERNAL)[0], "", "7.56"),
        )

    def test_rental_aliases_are_backend_authoritative(self):
        self.assertEqual(
            normalize_payroll_attendance_value("no scope", workspace=ATTENDANCE_WORKSPACE_RENTAL),
            (0, "N", "N"),
        )
        self.assertEqual(
            normalize_payroll_attendance_value("sick", workspace=ATTENDANCE_WORKSPACE_RENTAL),
            (0, "A", "A"),
        )

    def test_unknown_alphabetic_value_is_rejected_cleanly(self):
        with self.assertRaises(ValidationError):
            normalize_payroll_attendance_value("X", workspace=ATTENDANCE_WORKSPACE_INTERNAL)

    def test_workflow_aliases_normalize_to_one_contract(self):
        self.assertEqual(normalize_attendance_workflow_action("submit-for-review"), "submit")
        self.assertEqual(normalize_attendance_workflow_action("reject"), "return_to_draft")
        self.assertEqual(normalize_attendance_workflow_action("return"), "return_to_draft")
