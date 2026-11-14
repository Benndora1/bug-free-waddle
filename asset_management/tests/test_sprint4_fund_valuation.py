"""Integration tests for daily fund valuation, GAV/NAV math, and portfolio mark-to-market (Sprint 4)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from asset_management.tests.factories import (
	make_checker_user,
	make_fund,
	make_investor,
	make_security,
	make_security_price,
)


class TestSprint4FundValuation(IntegrationTestCase):
	def setUp(self) -> None:
		super().setUp()
		frappe.set_user("Administrator")
		self.dealer = make_checker_user("test_dealer@example.com")
		self.approver = make_checker_user("test_im@example.com")

		self.security = make_security(
			security_code="TEST-VAL-BOND-01",
			security_name="15.800% Treasury Bond 2039",
			instrument_type="Treasury Bond",
			asset_class="Treasury Bond",
			coupon_rate=15.800,
			coupon_rate_pct=15.800,
			current_market_price=93.547,
		)
		make_security_price(
			security=self.security.name,
			price_date=nowdate(),
			clean_price=93.547000,
			source="Central Bank",
		)

		self.fund_doc = make_fund(
			fund_id="TEST-S4-BND",
			fund_name="Test S4 Bond Scheme",
			fund_type="Fixed Income / Bond Fund",
			nav=0.0,
			total_units_in_issue=50000000.0,
			prior_day_valuation_approved=0,
			bid_offer_spread_pct=0.5,
			fee_schedule=[
				{
					"fee_type": "Management Fee",
					"calculation_basis": "GAV",
					"day_count_convention": "ACT/365F",
					"annual_percentage": 1.50,
					"accrual_frequency": "Daily",
				},
				{
					"fee_type": "Custody Fee",
					"calculation_basis": "GAV",
					"day_count_convention": "ACT/365F",
					"annual_percentage": 0.15,
					"accrual_frequency": "Daily",
				},
				{
					"fee_type": "Trustee Fee",
					"calculation_basis": "GAV",
					"day_count_convention": "ACT/365F",
					"annual_percentage": 0.10,
					"accrual_frequency": "Daily",
				},
				{
					"fee_type": "Regulatory Fee",
					"calculation_basis": "GAV",
					"day_count_convention": "ACT/365F",
					"annual_percentage": 0.05,
					"accrual_frequency": "Daily",
				},
				{
					"fee_type": "Audit Fee",
					"calculation_basis": "GAV",
					"day_count_convention": "ACT/365F",
					"annual_percentage": 0.05,
					"accrual_frequency": "Daily",
				},
			],
		)
		self.fund = self.fund_doc.name

		holding_name = f"{self.fund}-{self.security.name}"
		if frappe.db.exists("Asset Portfolio Holding", holding_name):
			h = frappe.get_doc("Asset Portfolio Holding", holding_name)
		else:
			h = frappe.new_doc("Asset Portfolio Holding")
			h.fund = self.fund
			h.security = self.security.name
		h.asset_class = "Treasury Bond"
		h.face_value = 5000000000.0
		h.carrying_cost = 4677350000.0
		h.accrued_interest = 69260273.97
		h.dirty_market_value = 4746610273.97
		h.holding_status = "Active"
		# Test setup: ignore_permissions required
		h.save(ignore_permissions=True) if not h.is_new() else h.insert(ignore_permissions=True)

		# Clean up any leftover draft valuations from earlier tests in the class
		for vname in frappe.get_all(
			"Asset Fund Valuation", filters={"fund": self.fund, "docstatus": 0}, pluck="name"
		):
			frappe.delete_doc("Asset Fund Valuation", vname, force=True, ignore_permissions=True)

		self.inv = make_investor(
			investor_id="__TEST_INV_S4_01",
			investor_name="Horizon Capital Management Ltd",
			investor_type="Corporate",
		)
		port_id = f"{self.inv.name}-{self.fund}"
		if not frappe.db.exists("Asset Investor Portfolio", port_id):
			p = frappe.new_doc("Asset Investor Portfolio")
			p.name = port_id
			p.investor = self.inv.name
			p.fund = self.fund
			p.total_units = 100000.0
			p.total_invested_amount = 10000000.0
			p.total_withdrawn_amount = 0.0
			p.current_nav_per_unit = 100.0
			p.current_market_value = 10000000.0
			# Test setup: ignore_permissions required
			p.insert(ignore_permissions=True)

	def test_01_gav_aggregation_across_multi_asset_classes(self) -> None:
		"""Verify automatic aggregation of portfolio holdings and cash into Gross Asset Value (GAV)."""
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = self.fund
		val.valuation_date = nowdate()
		val.cash_bank_balance = 1200000000.0
		val.accrued_income_receivable = 50000000.0
		# Test setup: ignore_permissions required
		val.insert(ignore_permissions=True)

		self.assertEqual(val.bonds_market_value, 4746610273.97)
		expected_gav = 4746610273.97 + 1200000000.0 + 50000000.0
		self.assertAlmostEqual(val.total_gav, expected_gav, places=2)
		self.assertGreater(len(val.lines), 0)
		self.assertAlmostEqual(
			sum(line.weight_pct for line in val.lines),
			(val.bonds_market_value / val.total_gav) * 100.0,
			places=1,
		)

	def test_02_daily_fee_accrual_nav_and_spread_mathematics(self) -> None:
		"""Verify daily expense accrual, NAV = GAV - Expenses, NAV/unit, and bid-offer spread pricing."""
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = self.fund
		val.valuation_date = nowdate()
		val.cash_bank_balance = 1000000000.0
		# Test setup: ignore_permissions required
		val.insert(ignore_permissions=True)

		gav = val.total_gav
		expected_mgmt = round(gav * 0.015 / 365.0, 2)
		expected_cust = round(gav * 0.0015 / 365.0, 2)
		expected_trust = round(gav * 0.0010 / 365.0, 2)
		expected_reg = round(gav * 0.0005 / 365.0, 2)
		expected_audit = round(gav * 0.0005 / 365.0, 2)

		self.assertAlmostEqual(val.management_fee_accrual, expected_mgmt, places=2)
		self.assertAlmostEqual(val.custody_fee_accrual, expected_cust, places=2)
		self.assertAlmostEqual(val.trustee_fee_accrual, expected_trust, places=2)
		self.assertAlmostEqual(val.cma_regulatory_fee_accrual, expected_reg, places=2)
		self.assertAlmostEqual(val.audit_fee_accrual, expected_audit, places=2)

		expected_total_exp = round(
			expected_mgmt + expected_cust + expected_trust + expected_reg + expected_audit, 2
		)
		self.assertAlmostEqual(val.total_accrued_expenses, expected_total_exp, places=2)

		expected_nav = round(val.total_gav - val.total_accrued_expenses, 2)
		self.assertEqual(val.total_nav, expected_nav)

		expected_nav_per_unit = round(expected_nav / 50000000.0, 6)
		self.assertAlmostEqual(val.nav_per_unit, expected_nav_per_unit, places=6)

		self.assertEqual(val.bid_offer_spread_pct, 0.5)
		expected_offer = round(val.nav_per_unit * 1.005, 6)
		expected_bid = round(val.nav_per_unit * 0.995, 6)
		self.assertAlmostEqual(val.offer_price, expected_offer, places=6)
		self.assertAlmostEqual(val.bid_price, expected_bid, places=6)

	def test_03_maker_checker_submission_portfolio_revaluation_and_cancellation(self) -> None:
		"""Verify Maker != Checker, Fund master update, portfolio revaluation, and cancellation."""
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = self.fund
		val.valuation_date = nowdate()
		val.cash_bank_balance = 1000000000.0
		val.prepared_by = self.dealer
		val.approved_by = self.dealer
		# Test setup: ignore_permissions required
		val.insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			val.submit()

		val.reload()
		val.approved_by = self.approver
		val.submit()
		self.assertEqual(val.status, "Approved")

		bnd = frappe.get_doc("Asset Fund", self.fund)
		self.assertEqual(bnd.prior_day_valuation_approved, 1)
		self.assertGreater(bnd.current_nav_per_unit, 100.0)
		self.assertEqual(str(bnd.last_valuation_date), nowdate())

		port = frappe.get_doc("Asset Investor Portfolio", f"{self.inv.name}-{self.fund}")
		self.assertEqual(port.current_nav_per_unit, bnd.current_nav_per_unit)
		expected_mkt_val = round(100000.0 * bnd.current_nav_per_unit, 2)
		self.assertEqual(port.current_market_value, expected_mkt_val)
		self.assertGreater(port.unrealized_gain_loss, 0.0)

		val.reload()
		val.cancel()
		self.assertEqual(val.status, "Cancelled")

	def test_04_valuation_with_zero_units_in_issue(self) -> None:
		"""Verify fund valuation handles zero units in issue without division-by-zero error."""
		empty_fund = make_fund(
			fund_id="TEST-EMPTY-SCHEME",
			fund_name="Test Empty Scheme",
			fund_type="Money Market Fund",
			nav=0.0,
			initial_nav_per_unit=100.0,
			total_units_in_issue=0.0,
		)

		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = empty_fund.name
		val.valuation_date = nowdate()
		# Test setup: ignore_permissions required
		val.insert(ignore_permissions=True)

		self.assertEqual(val.total_units_in_issue, 0.0)
		self.assertEqual(val.nav_per_unit, 100.0)
		self.assertEqual(val.offer_price, 100.0)

	def test_05_manual_override_of_receivables_and_liabilities(self) -> None:
		"""Verify custom receivables and liabilities adjust GAV and NAV accurately."""
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = self.fund
		val.valuation_date = nowdate()
		val.cash_bank_balance = 500000000.0
		val.accrued_income_receivable = 100000000.0
		val.other_liabilities = 25000000.0
		# Test setup: ignore_permissions required
		val.insert(ignore_permissions=True)

		self.assertEqual(val.accrued_income_receivable, 100000000.0)
		self.assertEqual(val.other_liabilities, 25000000.0)
		self.assertAlmostEqual(val.total_nav, val.total_gav - val.total_accrued_expenses, places=2)
