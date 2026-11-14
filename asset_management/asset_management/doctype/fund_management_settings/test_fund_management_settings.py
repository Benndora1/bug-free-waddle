"""Integration tests for Fund Management Settings Single DocType."""

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.tests.factories import make_fund_manager_company

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestFundManagementSettings(IntegrationTestCase):
	def test_fund_management_settings_validates_company_account_ownership(self) -> None:
		fm_comp = make_fund_manager_company("Test Settings FM")
		settings = frappe.get_single("Fund Management Settings")
		self.assertEqual(settings.fund_manager_company, fm_comp)
		self.assertTrue(bool(settings.commission_expense_account))
		self.assertTrue(bool(settings.commission_payable_account))
		self.assertEqual(settings.regulatory_fee_label, "Regulatory Fee")
