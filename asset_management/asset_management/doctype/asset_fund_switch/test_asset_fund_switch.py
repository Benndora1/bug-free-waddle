"""Integration tests for Asset Fund Switch DocType."""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.services.units import get_unit_balance
from asset_management.tests.factories import (
	make_checker_user,
	make_fund,
	make_investor,
	make_subscription,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetFundSwitch(IntegrationTestCase):
	def test_switch_moves_units_and_posts_gl_in_both_funds(self) -> None:
		checker = make_checker_user()
		fund_a = make_fund(fund_id="TEST-SW-A", nav=100.0, min_balance_amount=0.0)
		fund_b = make_fund(fund_id="TEST-SW-B", nav=50.0, min_balance_amount=0.0)
		inv = make_investor()

		make_subscription(inv.name, fund_a.name, amount=500000.0, checker_user=checker)

		swi = frappe.new_doc("Asset Fund Switch")
		swi.investor = inv.name
		swi.from_fund = fund_a.name
		swi.to_fund = fund_b.name
		swi.switch_by = "Units"
		swi.switch_units = 2000.0
		swi.maker = "Administrator"
		swi.checker = checker
		# Test setup: ignore_permissions required
		swi.insert(ignore_permissions=True)
		swi.approved_by_checker = 1
		swi.workflow_state = "Approved"
		swi.submit()

		self.assertEqual(get_unit_balance(inv.name, fund_a.name), Decimal("3000.000000"))
		self.assertEqual(get_unit_balance(inv.name, fund_b.name), Decimal("4000.000000"))
