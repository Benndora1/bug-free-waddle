"""Integration tests for Asset Investor Register Line DocType."""

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.tests.factories import (
	make_checker_user,
	make_fund,
	make_investor,
	make_subscription,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetInvestorRegisterLine(IntegrationTestCase):
	def test_subscription_creates_register_line_and_cancel_removes_it(self) -> None:
		checker = make_checker_user()
		fund = make_fund(fund_id="TEST-REG-MMF", nav=100.0)
		inv = make_investor()

		sub = make_subscription(inv.name, fund.name, amount=300000.0, checker_user=checker)
		lines = frappe.get_all("Asset Investor Register Line", filters={"voucher_no": sub.name})
		self.assertEqual(len(lines), 1)

		sub.reload()
		sub.cancel()
		lines_after = frappe.get_all("Asset Investor Register Line", filters={"voucher_no": sub.name})
		self.assertEqual(len(lines_after), 0)
