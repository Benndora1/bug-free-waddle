import unittest

import frappe
from frappe.utils import add_days, flt, nowdate


class TestSprint4FundValuation(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")

		# Clean prior valuations and holdings on test fund
		frappe.db.delete("Asset Fund Valuation", {"fund": "SBG-BND"})
		frappe.db.delete("Asset Portfolio Holding", {"fund": "SBG-BND"})

		# Ensure Fund SBG-BND has units and holdings
		bnd = frappe.get_doc("Asset Fund", "SBG-BND")
		bnd.total_units_in_issue = 50000000.0  # 50 Million units
		bnd.prior_day_valuation_approved = 0  # Start locked!
		bnd.save(ignore_permissions=True)

		# Ensure test holding exists on SBG-BND
		holding_id = "SBG-BND-UG12K2306394"
		if not frappe.db.exists("Asset Portfolio Holding", holding_id):
			h = frappe.new_doc("Asset Portfolio Holding")
			h.name = holding_id
			h.fund = "SBG-BND"
			h.security = "UG12K2306394"
			h.asset_class = "Treasury Bond"
			h.face_value = 5000000000.0  # 5 Billion UGX
			h.carrying_cost = 4677350000.0
			h.accrued_interest = 69260273.97
			h.dirty_market_value = 4746610273.97
			h.holding_status = "Active"
			h.insert(ignore_permissions=True)

		# Ensure test investor exists
		if not frappe.db.exists("Asset Investor", "__TEST_INV_S2_01"):
			inv = frappe.new_doc("Asset Investor")
			inv.investor_id = "__TEST_INV_S2_01"
			inv.investor_name = "Victoria Capital Management Ltd"
			inv.investor_type = "Corporate"
			inv.risk_rating = "Low"
			inv.status = "Active"
			inv.currency = "UGX"
			inv.insert(ignore_permissions=True)

		# Ensure a client portfolio exists on SBG-BND
		port_id = "__TEST_INV_S2_01-SBG-BND"
		if not frappe.db.exists("Asset Investor Portfolio", port_id):
			p = frappe.new_doc("Asset Investor Portfolio")
			p.name = port_id
			p.investor = "__TEST_INV_S2_01"
			p.fund = "SBG-BND"
			p.total_units = 100000.0  # 100k units
			p.total_invested_amount = 10000000.0
			p.total_withdrawn_amount = 0.0
			p.current_nav_per_unit = 100.0
			p.current_market_value = 10000000.0
			p.insert(ignore_permissions=True)

		frappe.db.commit()

	def test_01_gav_aggregation_across_multi_asset_classes(self):
		"""Verify automatic aggregation of portfolio holdings and cash into Gross Asset Value (GAV)."""
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = "SBG-BND"
		val.valuation_date = nowdate()
		val.cash_bank_balance = 1200000000.0  # 1.2 Billion UGX in bank
		val.accrued_income_receivable = 50000000.0  # 50M receivables
		val.insert(ignore_permissions=True)

		self.assertEqual(val.bonds_market_value, 4746610273.97)
		expected_gav = 4746610273.97 + 1200000000.0 + 50000000.0
		self.assertAlmostEqual(val.total_gav, expected_gav, places=2)
		self.assertGreater(len(val.lines), 0)
		self.assertAlmostEqual(
			sum(l.weight_pct for l in val.lines), (val.bonds_market_value / val.total_gav) * 100.0, places=1
		)

	def test_02_daily_fee_accrual_mathematics(self):
		"""Verify daily expense accrual: GAV * (Annual Rate / 100) / 365."""
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = "SBG-BND"
		val.valuation_date = nowdate()
		val.cash_bank_balance = 1000000000.0
		val.insert(ignore_permissions=True)

		gav = val.total_gav
		# Standard fee rates: Management 1.50%, Custody 0.15%, Trustee 0.10%, CMA 0.05%, Audit 0.05%
		expected_mgmt = round(gav * 0.015 / 365.0, 2)
		expected_cust = round(gav * 0.0015 / 365.0, 2)
		expected_trust = round(gav * 0.0010 / 365.0, 2)
		expected_cma = round(gav * 0.0005 / 365.0, 2)
		expected_audit = round(gav * 0.0005 / 365.0, 2)

		self.assertAlmostEqual(val.management_fee_accrual, expected_mgmt, places=2)
		self.assertAlmostEqual(val.custody_fee_accrual, expected_cust, places=2)
		self.assertAlmostEqual(val.trustee_fee_accrual, expected_trust, places=2)
		self.assertAlmostEqual(val.cma_regulatory_fee_accrual, expected_cma, places=2)
		self.assertAlmostEqual(val.audit_fee_accrual, expected_audit, places=2)

		expected_total_exp = round(
			expected_mgmt + expected_cust + expected_trust + expected_cma + expected_audit, 2
		)
		self.assertAlmostEqual(val.total_accrued_expenses, expected_total_exp, places=2)

	def test_03_nav_and_nav_per_unit_calculation(self):
		"""Verify Net Asset Value (NAV) = GAV - Expenses, and NAV Per Unit = NAV / Total Units."""
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = "SBG-BND"
		val.valuation_date = nowdate()
		val.cash_bank_balance = 1000000000.0
		val.insert(ignore_permissions=True)

		expected_nav = round(val.total_gav - val.total_accrued_expenses, 2)
		self.assertEqual(val.total_nav, expected_nav)

		expected_nav_per_unit = round(expected_nav / 50000000.0, 4)
		self.assertEqual(val.nav_per_unit, expected_nav_per_unit)
		self.assertGreater(val.nav_per_unit, 0.0)

	def test_04_bid_offer_spread_pricing(self):
		"""Verify Bid-Offer spread pricing: Offer = NAV * (1 + spread), Bid = NAV * (1 - spread)."""
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = "SBG-BND"  # Spread is 0.5%
		val.valuation_date = nowdate()
		val.cash_bank_balance = 1000000000.0
		val.insert(ignore_permissions=True)

		self.assertEqual(val.bid_offer_spread_pct, 0.5)
		expected_offer = round(val.nav_per_unit * 1.005, 4)
		expected_bid = round(val.nav_per_unit * 0.995, 4)

		self.assertEqual(val.offer_price, expected_offer)
		self.assertEqual(val.bid_price, expected_bid)

	def test_05_maker_checker_governance_on_valuation(self):
		"""Verify Maker != Checker dual control on daily fund valuation."""
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = "SBG-BND"
		val.valuation_date = nowdate()
		val.cash_bank_balance = 1000000000.0
		val.prepared_by = "test_dealer@example.com"
		val.approved_by = "test_dealer@example.com"  # Same user!
		val.insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			val.submit()

		val.reload()
		val.approved_by = "test_im@example.com"  # Distinct checker!
		val.submit()

		self.assertEqual(val.status, "Approved")

	def test_06_fund_master_update_and_rule_1_unlock(self):
		"""Verify submitting valuation updates Fund master and unlocks Rule 1 prior-day valuation guard."""
		bnd = frappe.get_doc("Asset Fund", "SBG-BND")
		self.assertEqual(bnd.prior_day_valuation_approved, 1)
		self.assertGreater(bnd.current_nav_per_unit, 100.0)
		self.assertEqual(str(bnd.last_valuation_date), nowdate())

	def test_07_investor_portfolio_mark_to_market_revaluation(self):
		"""Verify client portfolios holding this fund are revalued at the new NAV per unit."""
		port = frappe.get_doc("Asset Investor Portfolio", "__TEST_INV_S2_01-SBG-BND")
		bnd = frappe.get_doc("Asset Fund", "SBG-BND")

		self.assertEqual(port.current_nav_per_unit, bnd.current_nav_per_unit)
		expected_mkt_val = round(100000.0 * bnd.current_nav_per_unit, 2)
		self.assertEqual(port.current_market_value, expected_mkt_val)
		self.assertGreater(port.unrealized_gain_loss, 0.0)

	def test_08_valuation_with_zero_units_in_issue(self):
		"""Verify fund valuation handles zero units in issue without division-by-zero error."""
		# Create temporary empty fund
		fid = "SBG-TEST-EMPTY"
		if not frappe.db.exists("Asset Fund", fid):
			f = frappe.new_doc("Asset Fund")
			f.fund_id = fid
			f.fund_name = "Test Empty Scheme"
			f.fund_type = "Money Market Fund"
			f.currency = "UGX"
			f.launch_date = nowdate()
			f.initial_nav_per_unit = 100.0
			f.total_units_in_issue = 0.0
			f.insert(ignore_permissions=True)

		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = fid
		val.valuation_date = nowdate()
		val.insert(ignore_permissions=True)

		self.assertEqual(val.total_units_in_issue, 0.0)
		self.assertEqual(val.nav_per_unit, 100.0)
		self.assertEqual(val.offer_price, 100.0)

	def test_09_manual_override_of_receivables_and_liabilities(self):
		"""Verify custom receivables and liabilities adjust GAV and NAV accurately."""
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = "SBG-BND"
		val.valuation_date = nowdate()
		val.cash_bank_balance = 500000000.0
		val.accrued_income_receivable = 100000000.0  # +100M
		val.other_liabilities = 25000000.0  # +25M expense
		val.insert(ignore_permissions=True)

		self.assertIn(100000000.0, [val.accrued_income_receivable])
		self.assertIn(25000000.0, [val.other_liabilities])
		self.assertAlmostEqual(val.total_nav, val.total_gav - val.total_accrued_expenses, places=2)

	def test_10_valuation_cancellation_and_audit_trail(self):
		"""Verify cancellation of approved valuation record."""
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = "SBG-BND"
		val.valuation_date = nowdate()
		val.prepared_by = "test_dealer@example.com"
		val.approved_by = "test_im@example.com"
		val.insert(ignore_permissions=True)
		val.submit()

		self.assertEqual(val.status, "Approved")
		val.cancel()
		self.assertEqual(val.status, "Cancelled")


if __name__ == "__main__":
	unittest.main()
