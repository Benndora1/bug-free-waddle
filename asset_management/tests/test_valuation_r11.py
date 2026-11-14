"""Integration tests for daily fund valuation, price history, and GL postings (Task R-11)."""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from asset_management.services.pricing import get_applicable_bid_price, get_applicable_fund_price
from asset_management.tests.factories import (
	make_checker_user,
	make_fund,
	make_security,
	make_security_price,
)


class TestValuationR11(IntegrationTestCase):
	def setUp(self) -> None:
		super().setUp()
		frappe.set_user("Administrator")
		self.checker = make_checker_user()
		self.fund_code = "R11-MMF"
		self.security_code = "R11-BOND-01"

		make_security(
			security_code=self.security_code,
			security_name="R11 Treasury Bond 10Y",
			instrument_type="Treasury Bond",
			asset_class="Government Securities",
			coupon_rate_pct=14.0,
			current_market_price=100.0,
		)

		self.fund_doc = make_fund(
			fund_id=self.fund_code,
			fund_name="R11 Valuation Test Fund",
			fund_type="Money Market Fund",
			nav=0.0,
			total_units_in_issue=1000000.0,
			fee_schedule=[
				{
					"fee_type": "Management Fee",
					"calculation_basis": "GAV",
					"day_count_convention": "ACT/365F",
					"annual_percentage": 2.0,
					"accrual_frequency": "Daily",
				}
			],
		)

	def test_01_direct_fund_price_creation_blocked(self) -> None:
		"""Asset Fund Price can only be created by valuation submit."""
		fp = frappe.new_doc("Asset Fund Price")
		fp.fund = self.fund_code
		fp.price_date = "2026-11-05"
		fp.nav_per_unit = 100.0
		fp.bid_price = 100.0
		fp.offer_price = 100.0
		with self.assertRaises(frappe.ValidationError):
			fp.insert(ignore_permissions=True)

	def test_02_exact_1_day_and_3_day_accrual_d_minus_1_guard_and_latest_cancel(self) -> None:
		"""Exact R-11 checks:
		- GAV 100,000,000.00, management fee 2% ACT/365F, one day (Fri 2026-11-06) -> 5,479.45
		- Date D (Tue 2026-11-10) without approved D-1 (Mon 2026-11-09) fails
		- Friday (2026-11-06) to Monday (2026-11-09, 3 days) -> 16,438.36
		- Only the latest valuation can be cancelled
		"""
		val_fri = frappe.new_doc("Asset Fund Valuation")
		val_fri.fund = self.fund_code
		val_fri.valuation_date = "2026-11-06"
		val_fri.cash_bank_balance = 100000000.00
		val_fri.prepared_by = "Administrator"
		val_fri.approved_by = self.checker
		# Test setup: ignore_permissions required
		val_fri.insert(ignore_permissions=True)

		self.assertEqual(flt(val_fri.total_gav, 2), 100000000.00)
		self.assertEqual(flt(val_fri.management_fee_accrual, 2), 5479.45)
		self.assertEqual(flt(val_fri.total_accrued_expenses, 2), 5479.45)
		self.assertEqual(flt(val_fri.total_nav, 2), 99994520.55)
		val_fri.submit()

		self.assertTrue(
			frappe.db.exists("Asset Fund Price", {"fund": self.fund_code, "price_date": "2026-11-06"})
		)
		self.assertEqual(
			get_applicable_fund_price(self.fund_code, "2026-11-06"),
			Decimal("99.994521"),
		)
		self.assertEqual(
			get_applicable_bid_price(self.fund_code, "2026-11-06"),
			Decimal("99.994521"),
		)

		val_tue = frappe.new_doc("Asset Fund Valuation")
		val_tue.fund = self.fund_code
		val_tue.valuation_date = "2026-11-10"
		val_tue.cash_bank_balance = 100000000.00
		val_tue.prepared_by = "Administrator"
		val_tue.approved_by = self.checker
		# Test setup: ignore_permissions required
		val_tue.insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			val_tue.submit()

		val_mon = frappe.new_doc("Asset Fund Valuation")
		val_mon.fund = self.fund_code
		val_mon.valuation_date = "2026-11-09"
		val_mon.cash_bank_balance = 100000000.00
		val_mon.prepared_by = "Administrator"
		val_mon.approved_by = self.checker
		# Test setup: ignore_permissions required
		val_mon.insert(ignore_permissions=True)

		self.assertEqual(val_mon.accrual_days, 3)
		self.assertEqual(flt(val_mon.total_gav, 2), 100000000.00)
		self.assertEqual(flt(val_mon.management_fee_accrual, 2), 16438.36)
		self.assertEqual(flt(val_mon.total_accrued_expenses, 2), 16438.36)
		val_mon.submit()

		val_fri.reload()
		with self.assertRaises(frappe.ValidationError):
			val_fri.cancel()

		val_mon.reload()
		val_mon.cancel()
		self.assertEqual(val_mon.status, "Cancelled")

		val_fri.reload()
		val_fri.cancel()
		self.assertEqual(val_fri.status, "Cancelled")

	def test_03_missing_security_price_blocks_submit_and_gl_postings_reverse(self) -> None:
		"""Verify:
		- Holding without Asset Security Price on valuation_date blocks submit listing the security
		- Stale price within N days flags line when allowed in settings
		- GL posts Fee Expense, Interest Income, and MTM Revaluation, and reverses on cancel
		"""
		h = frappe.new_doc("Asset Portfolio Holding")
		h.fund = self.fund_code
		h.security = self.security_code
		h.asset_class = "Treasury Bond"
		h.face_value = 50000000.00
		h.carrying_cost = 50000000.00
		h.accrued_interest = 0.00
		h.dirty_market_value = 50000000.00
		h.holding_status = "Active"
		# Test setup: ignore_permissions required
		h.insert(ignore_permissions=True)

		val_missing = frappe.new_doc("Asset Fund Valuation")
		val_missing.fund = self.fund_code
		val_missing.valuation_date = "2026-11-06"
		val_missing.cash_bank_balance = 49000000.00
		val_missing.prepared_by = "Administrator"
		val_missing.approved_by = self.checker
		# Test setup: ignore_permissions required
		val_missing.insert(ignore_permissions=True)

		self.assertEqual(flt(val_missing.lines[0].price, 6), 0.0)
		with self.assertRaises(frappe.ValidationError) as ctx:
			val_missing.submit()
		self.assertIn(self.security_code, str(ctx.exception))

		make_security_price(
			security=self.security_code,
			price_date="2026-11-05",
			clean_price=101.000000,
			source="Exchange",
		)

		settings = frappe.get_single("Fund Management Settings")
		settings.allow_stale_security_prices = 1
		settings.max_stale_price_days = 3
		# Test setup: ignore_permissions required
		settings.save(ignore_permissions=True)
		try:
			val_stale = frappe.new_doc("Asset Fund Valuation")
			val_stale.fund = self.fund_code
			val_stale.valuation_date = "2026-11-06"
			val_stale.cash_bank_balance = 49500000.00
			# Test setup: ignore_permissions required
			val_stale.insert(ignore_permissions=True)
			self.assertEqual(val_stale.lines[0].is_stale_price, 1)
			self.assertEqual(str(val_stale.lines[0].price_date_used), "2026-11-05")
			self.assertEqual(flt(val_stale.lines[0].price, 6), 101.0)
		finally:
			settings.allow_stale_security_prices = 0
			settings.max_stale_price_days = 0
			# Test setup: ignore_permissions required
			settings.save(ignore_permissions=True)

		make_security_price(
			security=self.security_code,
			price_date="2026-11-06",
			clean_price=102.000000,
			source="Exchange",
		)

		val_ok = frappe.new_doc("Asset Fund Valuation")
		val_ok.fund = self.fund_code
		val_ok.valuation_date = "2026-11-06"
		val_ok.cash_bank_balance = 48900000.00
		val_ok.daily_interest_accrual = 100000.00
		val_ok.prepared_by = "Administrator"
		val_ok.approved_by = self.checker
		# Test setup: ignore_permissions required
		val_ok.insert(ignore_permissions=True)

		self.assertEqual(val_ok.lines[0].is_stale_price, 0)
		self.assertEqual(flt(val_ok.mtm_revaluation_change, 2), 1000000.00)
		self.assertEqual(flt(val_ok.total_gav, 2), 100000000.00)
		self.assertEqual(flt(val_ok.management_fee_accrual, 2), 5479.45)

		val_ok.submit()

		gl_rows = frappe.get_all(
			"GL Entry",
			filters={
				"voucher_type": "Asset Fund Valuation",
				"voucher_no": val_ok.name,
				"is_cancelled": 0,
			},
			fields=["account", "debit", "credit"],
		)
		self.assertEqual(len(gl_rows), 6)
		total_dr = sum(Decimal(str(r.debit)) for r in gl_rows)
		total_cr = sum(Decimal(str(r.credit)) for r in gl_rows)
		self.assertEqual(total_dr, Decimal("1105479.45"))
		self.assertEqual(total_cr, Decimal("1105479.45"))

		by_acc = {r.account: r for r in gl_rows}
		self.assertEqual(flt(by_acc[self.fund_doc.fees_payable_account].credit, 2), 5479.45)
		self.assertEqual(flt(by_acc[self.fund_doc.interest_receivable_account].debit, 2), 100000.00)
		self.assertEqual(flt(by_acc[self.fund_doc.interest_income_account].credit, 2), 100000.00)
		self.assertEqual(flt(by_acc[self.fund_doc.investment_revaluation_account].debit, 2), 1000000.00)
		self.assertEqual(flt(by_acc[self.fund_doc.unrealised_gain_loss_account].credit, 2), 1000000.00)

		val_ok.reload()
		val_ok.cancel()
		active_gl = frappe.get_all(
			"GL Entry",
			filters={
				"voucher_type": "Asset Fund Valuation",
				"voucher_no": val_ok.name,
				"is_cancelled": 0,
			},
		)
		self.assertEqual(len(active_gl), 0)
		self.assertFalse(
			frappe.db.exists("Asset Fund Price", {"fund": self.fund_code, "price_date": "2026-11-06"})
		)
