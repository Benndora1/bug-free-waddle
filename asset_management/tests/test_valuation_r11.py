import unittest
from decimal import Decimal

import frappe
from frappe.utils import flt

from asset_management.services.fund_setup import seed_default_account_templates, setup_fund_accounts
from asset_management.services.pricing import get_applicable_bid_price, get_applicable_fund_price


class TestValuationR11(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		frappe.set_user("Administrator")
		seed_default_account_templates()

		cls.fund_code = "R11-MMF"
		cls.security_code = "R11-BOND-01"
		cls._cleanup()

		# Create test security
		sec = frappe.new_doc("Asset Investment Security")
		sec.security_id = cls.security_code
		sec.security_name = "R11 Treasury Bond 10Y"
		sec.asset_class = "Treasury Bond"
		sec.issuer = "Bank of Uganda"
		sec.issuer_type = "Government"
		sec.sector = "Sovereign"
		sec.currency = "UGX"
		sec.issue_date = "2026-01-01"
		sec.maturity_date = "2036-01-01"
		sec.coupon_rate = 14.0
		sec.current_market_price = 100.0
		sec.status = "Active"
		sec.insert(ignore_permissions=True)

		# Create test fund with 2% Management Fee on GAV using ACT/365F
		fund = frappe.new_doc("Asset Fund")
		fund.fund_id = cls.fund_code
		fund.fund_name = "R11 Valuation Test Fund"
		fund.fund_type = "Money Market Fund"
		fund.currency = "UGX"
		fund.launch_date = "2026-01-01"
		fund.initial_nav_per_unit = 100.0
		fund.current_nav_per_unit = 100.0
		fund.current_bid_price = 100.0
		fund.current_offer_price = 100.0
		fund.bid_offer_spread_pct = 0.0
		fund.total_units_in_issue = 1000000.0
		fund.status = "Suspended"
		fund.append(
			"fees",
			{
				"fee_type": "Management Fee",
				"calculation_basis": "GAV",
				"day_count_convention": "ACT/365F",
				"annual_percentage": 2.0,
				"accrual_frequency": "Daily",
			},
		)
		fund.insert(ignore_permissions=True)
		setup_fund_accounts(cls.fund_code)
		frappe.db.set_value("Asset Fund", cls.fund_code, "status", "Active")

	@classmethod
	def tearDownClass(cls) -> None:
		cls._cleanup()

	@classmethod
	def _cleanup(cls) -> None:
		for val_name in frappe.get_all(
			"Asset Fund Valuation", filters={"fund": cls.fund_code}, pluck="name"
		):
			frappe.db.delete("GL Entry", {"voucher_type": "Asset Fund Valuation", "voucher_no": val_name})
			frappe.db.delete("Asset Fund Valuation Line", {"parent": val_name})
			frappe.db.delete("Asset Fund Valuation", {"name": val_name})

		for fp_name in frappe.get_all(
			"Asset Fund Price", filters={"fund": cls.fund_code}, pluck="name"
		):
			frappe.db.delete("Asset Fund Price", {"name": fp_name})

		for sp_name in frappe.get_all(
			"Asset Security Price", filters={"security": cls.security_code}, pluck="name"
		):
			frappe.db.delete("Asset Security Price", {"name": sp_name})

		for h_name in frappe.get_all(
			"Asset Portfolio Holding", filters={"fund": cls.fund_code}, pluck="name"
		):
			frappe.db.delete("Asset Portfolio Holding", {"name": h_name})

		frappe.db.delete("Asset Fund Fee Tier", {"parent": cls.fund_code})
		if frappe.db.exists("Asset Fund", cls.fund_code):
			frappe.db.delete("Asset Fund", {"name": cls.fund_code})

		if frappe.db.exists("Asset Investment Security", cls.security_code):
			frappe.db.delete("Asset Investment Security", {"name": cls.security_code})

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
		# 1. Friday 2026-11-06 (first valuation -> 1 day accrual)
		val_fri = frappe.new_doc("Asset Fund Valuation")
		val_fri.fund = self.fund_code
		val_fri.valuation_date = "2026-11-06"
		val_fri.cash_bank_balance = 100000000.00
		val_fri.prepared_by = "Administrator"
		val_fri.approved_by = "test_checker@example.com"
		val_fri.insert(ignore_permissions=True)

		self.assertEqual(flt(val_fri.total_gav, 2), 100000000.00)
		self.assertEqual(flt(val_fri.management_fee_accrual, 2), 5479.45)
		self.assertEqual(flt(val_fri.total_accrued_expenses, 2), 5479.45)
		self.assertEqual(flt(val_fri.total_nav, 2), 99994520.55)
		val_fri.submit()

		# Verify Asset Fund Price created and read by pricing.get_applicable_fund_price
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

		# 2. Attempting Tuesday 2026-11-10 without Monday 2026-11-09 (D-1 business day) fails
		val_tue = frappe.new_doc("Asset Fund Valuation")
		val_tue.fund = self.fund_code
		val_tue.valuation_date = "2026-11-10"
		val_tue.cash_bank_balance = 100000000.00
		val_tue.prepared_by = "Administrator"
		val_tue.approved_by = "test_checker@example.com"
		val_tue.insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			val_tue.submit()
		frappe.db.delete("Asset Fund Valuation", {"name": val_tue.name})

		# 3. Monday 2026-11-09 (3 days since Friday 2026-11-06 -> 16,438.36)
		val_mon = frappe.new_doc("Asset Fund Valuation")
		val_mon.fund = self.fund_code
		val_mon.valuation_date = "2026-11-09"
		val_mon.cash_bank_balance = 100000000.00
		val_mon.prepared_by = "Administrator"
		val_mon.approved_by = "test_checker@example.com"
		val_mon.insert(ignore_permissions=True)

		self.assertEqual(val_mon.accrual_days, 3)
		self.assertEqual(flt(val_mon.total_gav, 2), 100000000.00)
		self.assertEqual(flt(val_mon.management_fee_accrual, 2), 16438.36)
		self.assertEqual(flt(val_mon.total_accrued_expenses, 2), 16438.36)
		val_mon.submit()

		# 4. Cancelling Friday while Monday is Approved fails ("Only the latest valuation can be cancelled")
		val_fri.reload()
		with self.assertRaises(frappe.ValidationError):
			val_fri.cancel()

		# 5. Cancelling Monday (latest) succeeds, then cancelling Friday succeeds
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
		# Create active holding of 50,000,000 face value at carrying cost 50,000,000 (price 100.0)
		h = frappe.new_doc("Asset Portfolio Holding")
		h.fund = self.fund_code
		h.security = self.security_code
		h.asset_class = "Treasury Bond"
		h.face_value = 50000000.00
		h.carrying_cost = 50000000.00
		h.accrued_interest = 0.00
		h.dirty_market_value = 50000000.00
		h.holding_status = "Active"
		h.insert(ignore_permissions=True)

		try:
			# 1. Missing security price on 2026-11-06 blocks submit and lists R11-BOND-01
			val_missing = frappe.new_doc("Asset Fund Valuation")
			val_missing.fund = self.fund_code
			val_missing.valuation_date = "2026-11-06"
			val_missing.cash_bank_balance = 49000000.00
			val_missing.prepared_by = "Administrator"
			val_missing.approved_by = "test_checker@example.com"
			val_missing.insert(ignore_permissions=True)

			self.assertEqual(flt(val_missing.lines[0].price, 6), 0.0)
			with self.assertRaises(frappe.ValidationError) as ctx:
				val_missing.submit()
			self.assertIn(self.security_code, str(ctx.exception))
			frappe.db.delete("Asset Fund Valuation Line", {"parent": val_missing.name})
			frappe.db.delete("Asset Fund Valuation", {"name": val_missing.name})

			# 2. Publish Asset Security Price on 2026-11-05 (1 day prior) and test stale price allowance
			sp_prev = frappe.new_doc("Asset Security Price")
			sp_prev.security = self.security_code
			sp_prev.price_date = "2026-11-05"
			sp_prev.clean_price = 101.000000
			sp_prev.source = "USE"
			sp_prev.insert(ignore_permissions=True)

			settings = frappe.get_single("Fund Management Settings")
			settings.allow_stale_security_prices = 1
			settings.max_stale_price_days = 3
			settings.save(ignore_permissions=True)
			try:
				val_stale = frappe.new_doc("Asset Fund Valuation")
				val_stale.fund = self.fund_code
				val_stale.valuation_date = "2026-11-06"
				val_stale.cash_bank_balance = 49500000.00
				val_stale.insert(ignore_permissions=True)
				self.assertEqual(val_stale.lines[0].is_stale_price, 1)
				self.assertEqual(str(val_stale.lines[0].price_date_used), "2026-11-05")
				self.assertEqual(flt(val_stale.lines[0].price, 6), 101.0)
				frappe.db.delete("Asset Fund Valuation Line", {"parent": val_stale.name})
				frappe.db.delete("Asset Fund Valuation", {"name": val_stale.name})
			finally:
				settings.allow_stale_security_prices = 0
				settings.max_stale_price_days = 0
				settings.save(ignore_permissions=True)

			# 3. Publish exact Asset Security Price on 2026-11-06 at clean_price = 102.000000
			# Clean MV = 50,000,000 * 102 / 100 = 51,000,000.00 -> MTM gain = +1,000,000.00
			# Cash = 48,900,000.00, Daily Interest Accrual = 100,000.00 -> GAV = 100,000,000.00
			sp = frappe.new_doc("Asset Security Price")
			sp.security = self.security_code
			sp.price_date = "2026-11-06"
			sp.clean_price = 102.000000
			sp.source = "USE"
			sp.insert(ignore_permissions=True)

			val_ok = frappe.new_doc("Asset Fund Valuation")
			val_ok.fund = self.fund_code
			val_ok.valuation_date = "2026-11-06"
			val_ok.cash_bank_balance = 48900000.00
			val_ok.daily_interest_accrual = 100000.00
			val_ok.prepared_by = "Administrator"
			val_ok.approved_by = "test_checker@example.com"
			val_ok.insert(ignore_permissions=True)

			self.assertEqual(val_ok.lines[0].is_stale_price, 0)
			self.assertEqual(flt(val_ok.mtm_revaluation_change, 2), 1000000.00)
			self.assertEqual(flt(val_ok.total_gav, 2), 100000000.00)
			self.assertEqual(flt(val_ok.management_fee_accrual, 2), 5479.45)

			val_ok.submit()

			# Verify GL entries in fund's company (Fee accrual + Interest accrual + MTM revaluation = 6 rows)
			fund_doc = frappe.get_doc("Asset Fund", self.fund_code)
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
			self.assertEqual(flt(by_acc[fund_doc.fees_payable_account].credit, 2), 5479.45)
			self.assertEqual(flt(by_acc[fund_doc.interest_receivable_account].debit, 2), 100000.00)
			self.assertEqual(flt(by_acc[fund_doc.interest_income_account].credit, 2), 100000.00)
			self.assertEqual(flt(by_acc[fund_doc.investment_revaluation_account].debit, 2), 1000000.00)
			self.assertEqual(flt(by_acc[fund_doc.unrealised_gain_loss_account].credit, 2), 1000000.00)

			# Cancel reverses all GL entries and deletes Asset Fund Price
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
		finally:
			frappe.db.delete("Asset Portfolio Holding", {"name": h.name})
