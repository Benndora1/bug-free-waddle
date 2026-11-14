"""Integration tests for Asset BOL Import Header DocType."""

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.tests.factories import make_fund, make_investor

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetBOLImportHeader(IntegrationTestCase):
	def test_bol_parse_and_subscription_creation(self) -> None:
		fund = make_fund(fund_id="TEST-BOL-MMF", nav=100.0)
		inv = make_investor(investor_id="INV-BOL-01", bank_account_no="901000778899")

		csv_data = f"""Value Date,Transaction Description,Amount,Fund Code
2026-10-31,Deposit from 901000778899 client,{fund.min_subscription_amount * 2},{fund.name}
"""
		bol = frappe.new_doc("Asset BOL Import Header")
		bol.file_name = "BOL_TEST.csv"
		# Test setup: ignore_permissions required
		bol.insert(ignore_permissions=True)

		bol.parse_bol_statement(csv_data)
		self.assertEqual(bol.total_lines, 1)
		self.assertEqual(bol.matched_lines, 1)
		self.assertEqual(bol.lines[0].matched_investor, inv.name)

		res = bol.create_subscriptions()
		self.assertEqual(res["created_subscriptions"], 1)
