"""Integration tests for Asset Investor Portfolio DocType."""

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.tests.factories import (
	make_checker_user,
	make_fund,
	make_investor,
	make_subscription,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetInvestorPortfolio(IntegrationTestCase):
	def test_portfolio_rebuilt_from_unit_ledger(self) -> None:
		checker = make_checker_user()
		fund = make_fund(fund_id="TEST-PORT-MMF", nav=100.0)
		inv = make_investor()

		make_subscription(inv.name, fund.name, amount=250000.0, checker_user=checker)

		port = frappe.get_doc("Asset Investor Portfolio", f"{inv.name}-{fund.name}")
		self.assertEqual(port.total_units, 2500.0)
		self.assertEqual(port.current_market_value, 250000.0)
