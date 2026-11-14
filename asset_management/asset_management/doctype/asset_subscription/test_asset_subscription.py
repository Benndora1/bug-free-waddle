"""Integration tests for Asset Subscription DocType."""

from decimal import Decimal

from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from asset_management.services.units import get_unit_balance
from asset_management.tests.factories import (
	make_checker_user,
	make_fund,
	make_investor,
	make_subscription,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetSubscription(IntegrationTestCase):
	def test_subscription_allots_units_and_reverses_on_cancel(self) -> None:
		checker = make_checker_user()
		fund = make_fund(fund_id="TEST-SUB-DT", nav=100.0)
		inv = make_investor()

		sub = make_subscription(
			investor=inv.name,
			fund=fund.name,
			amount=500000.0,
			entry_fee_pct=2.0,
			checker_user=checker,
		)
		self.assertEqual(flt(sub.entry_fee_amount, 2), 10000.0)
		self.assertEqual(flt(sub.net_invested_amount, 2), 490000.0)
		self.assertEqual(get_unit_balance(inv.name, fund.name), Decimal("4900.000000"))

		sub.reload()
		sub.cancel()
		self.assertEqual(get_unit_balance(inv.name, fund.name), Decimal("0.000000"))
