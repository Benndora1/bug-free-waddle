"""Integration tests for immutable unit ledger and services.units."""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from asset_management.services.units import (
	get_unit_balance,
	make_unit_ledger_entry,
	rebuild_portfolio,
)
from asset_management.tests.factories import make_checker_user, make_fund, make_investor


class TestUnitsService(IntegrationTestCase):
	def setUp(self) -> None:
		super().setUp()
		frappe.set_user("Administrator")
		self.checker = make_checker_user()
		self.fund_doc = make_fund(
			fund_id="TEST-ULE-MMF",
			fund_name="Test Unit Ledger MMF",
			nav=100.0,
			bid=100.0,
			offer=100.0,
		)
		self.fund = self.fund_doc.name
		self.inv_doc = make_investor(investor_name="Unit Ledger Test Investor")
		self.investor = self.inv_doc.name

	def test_01_subscribe_redeem_cancel_ledger_lifecycle(self) -> None:
		"""Test subscribing 10,000 units, redeeming 4,000.5, cancelling redemption.

		Asserts balance is exactly Decimal('10000.000000') and ledger holds 3 rows.
		"""
		sub = frappe.new_doc("Asset Subscription")
		sub.investor = self.investor
		sub.fund = self.fund
		sub.subscription_date = nowdate()
		sub.gross_amount = 1000000.0
		sub.maker = "Administrator"
		sub.checker = self.checker
		sub.payment_received = 1
		# Test setup: ignore_permissions required
		sub.insert(ignore_permissions=True)

		sub.approved_by_operations = 1
		sub.workflow_state = "Approved"
		sub.submit()

		balance_after_sub = get_unit_balance(self.investor, self.fund)
		self.assertEqual(balance_after_sub, Decimal("10000.000000"))

		red = frappe.new_doc("Asset Redemption")
		red.investor = self.investor
		red.fund = self.fund
		red.redemption_date = nowdate()
		red.prior_day_valuation_approved = 1
		red.redemption_by = "Units"
		red.requested_units = 4000.5
		red.maker = "Administrator"
		red.checker = self.checker
		# Test setup: ignore_permissions required
		red.insert(ignore_permissions=True)

		red.checker_approved = 1
		red.workflow_state = "Approved"
		red.submit()

		balance_after_red = get_unit_balance(self.investor, self.fund)
		self.assertEqual(balance_after_red, Decimal("5999.500000"))

		red.cancel()

		balance_after_cancel = get_unit_balance(self.investor, self.fund)
		self.assertEqual(balance_after_cancel, Decimal("10000.000000"))

		entries = frappe.get_all(
			"Asset Unit Ledger Entry",
			filters={"investor": self.investor, "fund": self.fund},
			fields=["name", "voucher_type", "voucher_no", "entry_type", "units", "is_cancelled"],
			order_by="creation asc",
		)
		self.assertEqual(len(entries), 3)
		self.assertEqual(entries[0]["voucher_type"], "Asset Subscription")
		self.assertEqual(entries[0]["units"], 10000.0)
		self.assertEqual(entries[0]["is_cancelled"], 0)
		self.assertEqual(entries[1]["voucher_type"], "Asset Redemption")
		self.assertEqual(entries[1]["units"], -4000.5)
		self.assertEqual(entries[1]["is_cancelled"], 1)
		self.assertEqual(entries[2]["voucher_type"], "Asset Redemption")
		self.assertEqual(entries[2]["units"], 4000.5)
		self.assertEqual(entries[2]["is_cancelled"], 0)

		portfolio_id = f"{self.investor}-{self.fund}"
		port = frappe.get_doc("Asset Investor Portfolio", portfolio_id)
		self.assertEqual(port.total_units, 10000.0)
		self.assertEqual(port.total_invested_amount, 1000000.0)
		self.assertEqual(port.total_withdrawn_amount, 0.0)

	def test_02_backdated_subscription_as_of_balances(self) -> None:
		"""Verify as-of date unit balance calculations with backdated entries."""
		day1 = "2026-06-01"
		day2 = "2026-06-02"
		day3 = "2026-06-03"

		class MockVoucher:
			doctype = "Asset Subscription"
			name = "MOCK-SUB-DAY1"
			posting_date = day1

		make_unit_ledger_entry(
			MockVoucher,
			[
				{
					"investor": self.investor,
					"fund": self.fund,
					"entry_type": "Subscription",
					"units": 5000.0,
					"price_per_unit": 100.0,
					"amount": 500000.0,
					"posting_date": day1,
				}
			],
		)

		class MockRedemption:
			doctype = "Asset Redemption"
			name = "MOCK-RED-DAY3"
			posting_date = day3

		make_unit_ledger_entry(
			MockRedemption,
			[
				{
					"investor": self.investor,
					"fund": self.fund,
					"entry_type": "Redemption",
					"units": -2000.0,
					"price_per_unit": 100.0,
					"amount": 200000.0,
					"posting_date": day3,
				}
			],
		)

		self.assertEqual(get_unit_balance(self.investor, self.fund, as_of_date=day1), Decimal("5000.000000"))
		self.assertEqual(get_unit_balance(self.investor, self.fund, as_of_date=day3), Decimal("3000.000000"))

		class MockBackdatedSub:
			doctype = "Asset Subscription"
			name = "MOCK-SUB-DAY2"
			posting_date = day2

		make_unit_ledger_entry(
			MockBackdatedSub,
			[
				{
					"investor": self.investor,
					"fund": self.fund,
					"entry_type": "Subscription",
					"units": 10000.0,
					"price_per_unit": 100.0,
					"amount": 1000000.0,
					"posting_date": day2,
				}
			],
		)

		self.assertEqual(get_unit_balance(self.investor, self.fund, as_of_date=day1), Decimal("5000.000000"))
		self.assertEqual(get_unit_balance(self.investor, self.fund, as_of_date=day2), Decimal("15000.000000"))
		self.assertEqual(get_unit_balance(self.investor, self.fund, as_of_date=day3), Decimal("13000.000000"))

	def test_03_redemption_insufficient_units_guard(self) -> None:
		"""Verify that a redemption larger than get_unit_balance at its date fails with a clear error."""

		class MockVoucher:
			doctype = "Asset Subscription"
			name = "MOCK-SUB-GUARD"
			posting_date = nowdate()

		make_unit_ledger_entry(
			MockVoucher,
			[
				{
					"investor": self.investor,
					"fund": self.fund,
					"entry_type": "Subscription",
					"units": 1000.0,
					"price_per_unit": 100.0,
					"amount": 100000.0,
					"posting_date": nowdate(),
				}
			],
		)
		rebuild_portfolio(self.investor, self.fund)

		red = frappe.new_doc("Asset Redemption")
		red.investor = self.investor
		red.fund = self.fund
		red.redemption_date = nowdate()
		red.prior_day_valuation_approved = 1
		red.redemption_by = "Units"
		red.requested_units = 1500.0
		red.applicable_bid_price = 100.0
		red.maker = "Administrator"
		red.checker = self.checker

		with self.assertRaises(frappe.ValidationError) as ctx:
			red.insert(ignore_permissions=True)

		self.assertIn("Insufficient units", str(ctx.exception))
