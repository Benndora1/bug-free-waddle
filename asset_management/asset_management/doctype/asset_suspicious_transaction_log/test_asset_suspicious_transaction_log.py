"""Integration tests for Asset Suspicious Transaction Log DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from asset_management.tests.factories import make_fund

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetSuspiciousTransactionLog(IntegrationTestCase):
	def test_unallocated_bol_deposit_creates_suspicious_transaction_log(self) -> None:
		fund = make_fund(fund_id="TEST-STL-MMF", nav=100.0)
		bol = frappe.new_doc("Asset BOL Import Header")
		bol.file_name = "STL_TEST.csv"
		# Test setup: ignore_permissions required
		bol.insert(ignore_permissions=True)

		three_days_ago = add_days(nowdate(), -3)
		bol.append(
			"lines",
			{
				"line_no": 1,
				"value_date": three_days_ago,
				"transaction_description": "Unmatched wire 991122",
				"amount": 1000000.0,
				"fund_code": fund.name,
				"status": "Exception",
				"exception_reason": "No client match",
				"unallocated_since": three_days_ago,
			},
		)
		# Test setup: ignore_permissions required
		bol.save(ignore_permissions=True)

		res = bol.check_unallocated_sla(threshold_hours=48.0)
		self.assertEqual(res["escalated_count"], 1)
		self.assertTrue(
			frappe.db.exists(
				"Asset Suspicious Transaction Log",
				{"transaction_reference": f"{bol.name}-1"},
			)
		)
