"""Integration tests for Asset Fund Valuation DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from asset_management.tests.factories import make_checker_user, make_fund

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetFundValuation(IntegrationTestCase):
	def test_valuation_accrual_and_price_publication(self) -> None:
		checker = make_checker_user()
		fund = make_fund(
			fund_id="TEST-DT-VAL",
			nav=0.0,
			total_units_in_issue=100000.0,
			fee_schedule=[
				{
					"fee_type": "Management Fee",
					"calculation_basis": "GAV",
					"day_count_convention": "ACT/365F",
					"annual_percentage": 3.65,
					"accrual_frequency": "Daily",
				}
			],
		)

		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = fund.name
		val.valuation_date = "2026-11-06"
		val.cash_bank_balance = 10000000.0
		val.prepared_by = "Administrator"
		val.approved_by = checker
		# Test setup: ignore_permissions required
		val.insert(ignore_permissions=True)

		self.assertEqual(flt(val.management_fee_accrual, 2), 1000.00)
		val.submit()
		self.assertTrue(frappe.db.exists("Asset Fund Price", {"fund": fund.name, "price_date": "2026-11-06"}))
