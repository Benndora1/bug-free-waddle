"""Integration tests for Asset Redemption DocType."""

from decimal import Decimal

from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from asset_management.services.units import get_unit_balance
from asset_management.tests.factories import (
	make_checker_user,
	make_fund,
	make_investor,
	make_redemption,
	make_subscription,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetRedemption(IntegrationTestCase):
	def test_redemption_reduces_units_and_posts_gl(self) -> None:
		checker = make_checker_user()
		fund = make_fund(fund_id="TEST-RED-DT", nav=100.0, min_balance_amount=0.0)
		inv = make_investor()

		make_subscription(inv.name, fund.name, amount=500000.0, checker_user=checker)
		red = make_redemption(
			investor=inv.name,
			fund=fund.name,
			units=2000.0,
			exit_fee_pct=1.0,
			checker_user=checker,
		)

		self.assertEqual(flt(red.gross_redemption_amount, 2), 200000.0)
		self.assertEqual(flt(red.exit_fee_amount, 2), 2000.0)
		self.assertEqual(flt(red.net_payout_amount, 2), 198000.0)
		self.assertEqual(get_unit_balance(inv.name, fund.name), Decimal("3000.000000"))
