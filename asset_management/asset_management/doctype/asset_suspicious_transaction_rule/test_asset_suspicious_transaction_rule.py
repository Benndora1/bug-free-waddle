"""Integration tests for Asset Suspicious Transaction Rule DocType."""

import frappe
from frappe.tests import IntegrationTestCase

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetSuspiciousTransactionRule(IntegrationTestCase):
	def test_suspicious_transaction_rule_creation_and_threshold(self) -> None:
		self.assertTrue(frappe.db.exists("Asset Suspicious Transaction Rule", "AML_LARGE_CASH"))
		rule = frappe.get_doc("Asset Suspicious Transaction Rule", "AML_LARGE_CASH")
		self.assertEqual(rule.active, 1)
		self.assertGreater(rule.threshold_amount, 0.0)
