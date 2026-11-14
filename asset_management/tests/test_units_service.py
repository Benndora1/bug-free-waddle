"""Unit tests for immutable unit ledger and services.units."""

import unittest
from decimal import Decimal

import frappe
from frappe.utils import add_days, nowdate

from asset_management.services.units import (
	get_fund_units_in_issue,
	get_unit_balance,
	make_unit_ledger_entry,
	rebuild_portfolio,
	reverse_unit_ledger_entries,
)


class TestUnitsService(unittest.TestCase):
	def setUp(self):
		"""Set up isolated test fixtures."""
		frappe.set_user("Administrator")
		self.investor = "__TEST_ULE_INV_01"
		self.fund = "SBG-MMF"

		# Ensure test investor exists
		if not frappe.db.exists("Asset Investor", self.investor):
			inv = frappe.new_doc("Asset Investor")
			inv.investor_id = self.investor
			inv.investor_name = "Unit Ledger Test Investor"
			inv.investor_type = "Individual"
			inv.email = "ule_test@example.com"
			inv.phone = "+256700000099"
			inv.status = "Active"
			inv.insert(ignore_permissions=True)

		# Ensure Fund prices are baseline 100.0
		fund_doc = frappe.get_doc("Asset Fund", self.fund)
		fund_doc.current_offer_price = 100.0
		fund_doc.current_bid_price = 100.0
		fund_doc.current_nav_per_unit = 100.0
		fund_doc.last_valuation_date = nowdate()
		fund_doc.save(ignore_permissions=True)

		# Clean any prior test unit ledger entries for this investor
		frappe.db.delete("Asset Unit Ledger Entry", {"investor": self.investor})
		portfolio_id = f"{self.investor}-{self.fund}"
		if frappe.db.exists("Asset Investor Portfolio", portfolio_id):
			frappe.db.delete("Asset Investor Portfolio", {"name": portfolio_id})
		frappe.db.commit()

	def test_01_subscribe_redeem_cancel_ledger_lifecycle(self):
		"""Test subscribing 10,000 units, redeeming 4,000.5, cancelling redemption.

		Asserts balance is exactly Decimal('10000.000000') and ledger holds exactly 3 rows.
		"""
		# 1. Subscribe 10,000 units (fund NAV is 100.0 for SBG-MMF -> 1,000,000 UGX = 10,000 units)
		sub = frappe.new_doc("Asset Subscription")
		sub.investor = self.investor
		sub.fund = self.fund
		sub.subscription_date = nowdate()
		sub.gross_amount = 1000000.0  # 1M at NAV 100.0 = 10,000 units
		sub.maker = "Administrator"
		sub.checker = "test_checker@example.com"
		sub.payment_received = 1
		sub.insert(ignore_permissions=True)

		sub.approved_by_operations = 1
		sub.workflow_state = "Approved"
		sub.submit()

		# Verify balance is 10,000.000000
		balance_after_sub = get_unit_balance(self.investor, self.fund)
		self.assertEqual(balance_after_sub, Decimal("10000.000000"))

		# 2. Redeem 4,000.5 units
		red = frappe.new_doc("Asset Redemption")
		red.investor = self.investor
		red.fund = self.fund
		red.redemption_date = nowdate()
		red.prior_day_valuation_approved = 1
		red.redemption_by = "Units"
		red.requested_units = 4000.5
		red.maker = "Administrator"
		red.checker = "test_checker@example.com"
		red.insert(ignore_permissions=True)

		red.checker_approved = 1
		red.workflow_state = "Approved"
		red.submit()

		# Verify balance is 5,999.500000
		balance_after_red = get_unit_balance(self.investor, self.fund)
		self.assertEqual(balance_after_red, Decimal("5999.500000"))

		# 3. Cancel the redemption
		red.cancel()

		# Verify balance is restored to exactly 10,000.000000
		balance_after_cancel = get_unit_balance(self.investor, self.fund)
		self.assertEqual(balance_after_cancel, Decimal("10000.000000"))

		# Verify the ledger holds exactly 3 rows:
		# Row 1: Subscription (+10,000, is_cancelled=0)
		# Row 2: Redemption (-4,000.5, is_cancelled=1)
		# Row 3: Reversal (+4,000.5, is_cancelled=0)
		entries = frappe.get_all(
			"Asset Unit Ledger Entry",
			filters={"investor": self.investor, "fund": self.fund},
			fields=["name", "voucher_type", "voucher_no", "entry_type", "units", "is_cancelled"],
			order_by="creation asc",
		)
		self.assertEqual(len(entries), 3)

		# Subscription entry
		self.assertEqual(entries[0]["voucher_type"], "Asset Subscription")
		self.assertEqual(entries[0]["voucher_no"], sub.name)
		self.assertEqual(entries[0]["units"], 10000.0)
		self.assertEqual(entries[0]["is_cancelled"], 0)

		# Original redemption entry (flagged is_cancelled=1, units preserved)
		self.assertEqual(entries[1]["voucher_type"], "Asset Redemption")
		self.assertEqual(entries[1]["voucher_no"], red.name)
		self.assertEqual(entries[1]["units"], -4000.5)
		self.assertEqual(entries[1]["is_cancelled"], 1)

		# Reversal entry (negating row, +4000.5 units, is_cancelled=0)
		self.assertEqual(entries[2]["voucher_type"], "Asset Redemption")
		self.assertEqual(entries[2]["voucher_no"], red.name)
		self.assertEqual(entries[2]["units"], 4000.5)
		self.assertEqual(entries[2]["is_cancelled"], 0)

		# Verify portfolio reflects exact rebuilt numbers
		portfolio_id = f"{self.investor}-{self.fund}"
		port = frappe.get_doc("Asset Investor Portfolio", portfolio_id)
		self.assertEqual(port.total_units, 10000.0)
		self.assertEqual(port.total_invested_amount, 1000000.0)
		self.assertEqual(port.total_withdrawn_amount, 0.0)

	def test_02_backdated_subscription_as_of_balances(self):
		"""Verify as-of date unit balance calculations with backdated entries."""
		day1 = "2026-06-01"
		day2 = "2026-06-02"
		day3 = "2026-06-03"

		# Create mock voucher for testing pure service functions
		class MockVoucher:
			doctype = "Asset Subscription"
			name = "MOCK-SUB-DAY1"
			posting_date = day1

		# Day 1: Subscription 5,000 units
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

		# Day 3: Redemption 2,000 units
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

		# Before backdating: balance on Day 1 is 5,000; balance on Day 3 is 3,000
		self.assertEqual(get_unit_balance(self.investor, self.fund, as_of_date=day1), Decimal("5000.000000"))
		self.assertEqual(get_unit_balance(self.investor, self.fund, as_of_date=day3), Decimal("3000.000000"))

		# Day 2: Backdated subscription 10,000 units posted
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

		# Check as-of balances on all dates:
		# Day 1: 5,000
		self.assertEqual(get_unit_balance(self.investor, self.fund, as_of_date=day1), Decimal("5000.000000"))
		# Day 2: 5,000 + 10,000 = 15,000
		self.assertEqual(get_unit_balance(self.investor, self.fund, as_of_date=day2), Decimal("15000.000000"))
		# Day 3: 15,000 - 2,000 = 13,000
		self.assertEqual(get_unit_balance(self.investor, self.fund, as_of_date=day3), Decimal("13000.000000"))

	def test_03_redemption_insufficient_units_guard(self):
		"""Verify that a redemption larger than get_unit_balance at its date fails with a clear error."""

		# 1. Provide initial balance of 1,000 units
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

		# 2. Attempt redemption of 1,500 units -> Must fail validation
		red = frappe.new_doc("Asset Redemption")
		red.investor = self.investor
		red.fund = self.fund
		red.redemption_date = nowdate()
		red.prior_day_valuation_approved = 1
		red.redemption_by = "Units"
		red.requested_units = 1500.0
		red.applicable_bid_price = 100.0
		red.maker = "Administrator"
		red.checker = "test_checker@example.com"

		with self.assertRaises(frappe.ValidationError) as ctx:
			red.insert(ignore_permissions=True)

		self.assertIn("Insufficient units", str(ctx.exception))
