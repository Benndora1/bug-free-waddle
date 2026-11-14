"""Integration tests for Asset Fund DocType."""

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.tests.factories import make_fund

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetFund(IntegrationTestCase):
	def test_fund_spread_pricing_and_account_guard(self) -> None:
		fund = make_fund(
			fund_id="TEST-DT-BAL",
			fund_name="Test DocType Balanced Fund",
			fund_type="Balanced Fund",
			nav=200.0,
			bid_offer_spread_pct=1.5,
		)
		self.assertAlmostEqual(fund.current_offer_price, 203.0, places=4)
		self.assertAlmostEqual(fund.current_bid_price, 197.0, places=4)
		self.assertTrue(bool(fund.company))
		self.assertTrue(bool(fund.client_cash_payable_account))
