"""Integration tests for daily fund NAV vs GL reconciliation and report (Task R-12)."""

from typing import Any

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.asset_management.report.fund_nav_reconciliation.fund_nav_reconciliation import (
	execute as run_recon_report,
)
from asset_management.services.reconciliation import reconcile_fund
from asset_management.tests.factories import make_checker_user, make_fund, make_investor


class TestReconciliationR12(IntegrationTestCase):
	def setUp(self) -> None:
		super().setUp()
		frappe.set_user("Administrator")
		self.checker = make_checker_user()
		self.inv_doc = make_investor(investor_name="R12 Reconciliation Investor")
		self.investor_id = self.inv_doc.name

		self.fund_a_code = "R12-MMF-A"
		self.fund_b_code = "R12-BAL-B"

		self.fund_a_doc = make_fund(
			fund_id=self.fund_a_code,
			fund_name="R12 Reconciliation Fund A",
			fund_type="Money Market Fund",
			nav=0.0,
			initial_nav_per_unit=100.0,
			current_nav_per_unit=100.0,
			current_bid_price=100.0,
			current_offer_price=100.0,
			bid_offer_spread_pct=0.0,
			min_subscription_amount=100000.0,
			min_additional_amount=50000.0,
			min_redemption_amount=50000.0,
			min_balance_amount=0.0,
			wht_basis="None",
			wht_rate=0.0,
			last_valuation_date="2026-11-02",
			fee_schedule=[
				{
					"fee_type": "Management Fee",
					"calculation_basis": "GAV",
					"day_count_convention": "ACT/365F",
					"annual_percentage": 1.825,
					"accrual_frequency": "Daily",
				}
			],
		)
		frappe.db.set_value("Asset Fund", self.fund_a_code, "last_valuation_date", "2026-11-02")

		self.fund_b_doc = make_fund(
			fund_id=self.fund_b_code,
			fund_name="R12 Reconciliation Fund B",
			fund_type="Balanced Fund",
			nav=0.0,
			initial_nav_per_unit=50.0,
			current_nav_per_unit=50.0,
			current_bid_price=50.0,
			current_offer_price=50.0,
			bid_offer_spread_pct=0.0,
			min_subscription_amount=100000.0,
			min_additional_amount=50000.0,
			min_redemption_amount=50000.0,
			min_balance_amount=0.0,
			wht_basis="None",
			wht_rate=0.0,
			last_valuation_date="2026-11-05",
			fee_schedule=[],
		)
		frappe.db.set_value("Asset Fund", self.fund_b_code, "last_valuation_date", "2026-11-05")

	def _submit_valuation(self, fund_code: str, val_date: str, interest_accrual: float = 0.0) -> Any:
		val = frappe.new_doc("Asset Fund Valuation")
		val.fund = fund_code
		val.valuation_date = val_date
		val.daily_interest_accrual = interest_accrual
		val.prepared_by = "Administrator"
		val.approved_by = self.checker
		# Test setup: ignore_permissions required
		val.insert(ignore_permissions=True)
		val.submit()
		return val

	def test_01_five_day_lifecycle_reconciles_daily_and_manual_je_breaks_next_day(self) -> None:
		"""5-day scenario (subscriptions, a redemption, a switch, daily valuations) reconciles every day;
		posting a manual Journal Entry to the fund's investment account makes the next day fail with the difference shown.
		"""
		# Day 1 (Mon 2026-11-02)
		sub1 = frappe.new_doc("Asset Subscription")
		sub1.investor = self.investor_id
		sub1.fund = self.fund_a_code
		sub1.subscription_date = "2026-11-02"
		sub1.gross_amount = 1000000.00
		sub1.entry_fee_pct = 0.0
		sub1.maker = "Administrator"
		sub1.checker = self.checker
		# Test setup: ignore_permissions required
		sub1.insert(ignore_permissions=True)
		sub1.checker_approved = 1
		sub1.workflow_state = "Approved"
		sub1.submit()

		self._submit_valuation(self.fund_a_code, "2026-11-02", interest_accrual=1500.00)
		rec_d1 = reconcile_fund(self.fund_a_code, "2026-11-02")
		self.assertTrue(rec_d1["within_tolerance"], f"Day 1 failed: {rec_d1}")

		# Day 2 (Tue 2026-11-03)
		frappe.db.set_value("Asset Fund", self.fund_a_code, "last_valuation_date", "2026-11-03")
		sub2 = frappe.new_doc("Asset Subscription")
		sub2.investor = self.investor_id
		sub2.fund = self.fund_a_code
		sub2.subscription_date = "2026-11-03"
		sub2.gross_amount = 500000.00
		sub2.entry_fee_pct = 0.0
		sub2.maker = "Administrator"
		sub2.checker = self.checker
		# Test setup: ignore_permissions required
		sub2.insert(ignore_permissions=True)
		sub2.checker_approved = 1
		sub2.workflow_state = "Approved"
		sub2.submit()

		self._submit_valuation(self.fund_a_code, "2026-11-03", interest_accrual=2000.00)
		rec_d2 = reconcile_fund(self.fund_a_code, "2026-11-03")
		self.assertTrue(rec_d2["within_tolerance"], f"Day 2 failed: {rec_d2}")

		# Day 3 (Wed 2026-11-04)
		frappe.db.set_value("Asset Fund", self.fund_a_code, "last_valuation_date", "2026-11-04")
		red = frappe.new_doc("Asset Redemption")
		red.investor = self.investor_id
		red.fund = self.fund_a_code
		red.redemption_date = "2026-11-04"
		red.redemption_by = "Units"
		red.requested_units = 2000.0
		red.exit_fee_pct = 0.0
		red.prior_day_valuation_approved = 1
		red.maker = "Administrator"
		red.checker = self.checker
		# Test setup: ignore_permissions required
		red.insert(ignore_permissions=True)
		red.checker_approved = 1
		red.workflow_state = "Approved"
		red.submit()

		self._submit_valuation(self.fund_a_code, "2026-11-04", interest_accrual=1800.00)
		rec_d3 = reconcile_fund(self.fund_a_code, "2026-11-04")
		self.assertTrue(rec_d3["within_tolerance"], f"Day 3 failed: {rec_d3}")

		# Day 4 (Thu 2026-11-05)
		frappe.db.set_value("Asset Fund", self.fund_a_code, "last_valuation_date", "2026-11-05")
		frappe.db.set_value("Asset Fund", self.fund_b_code, "last_valuation_date", "2026-11-05")
		swi = frappe.new_doc("Asset Fund Switch")
		swi.investor = self.investor_id
		swi.from_fund = self.fund_a_code
		swi.to_fund = self.fund_b_code
		swi.switch_date = "2026-11-05"
		swi.switch_by = "Units"
		swi.switch_units = 1000.0
		swi.switch_fee_pct = 0.0
		swi.entry_fee_pct = 0.0
		swi.maker = "Administrator"
		swi.checker = self.checker
		# Test setup: ignore_permissions required
		swi.insert(ignore_permissions=True)
		swi.approved_by_checker = 1
		swi.workflow_state = "Approved"
		swi.submit()

		self._submit_valuation(self.fund_a_code, "2026-11-05", interest_accrual=1600.00)
		rec_d4 = reconcile_fund(self.fund_a_code, "2026-11-05")
		self.assertTrue(rec_d4["within_tolerance"], f"Day 4 failed: {rec_d4}")

		# Day 5 (Fri 2026-11-06)
		self._submit_valuation(self.fund_a_code, "2026-11-06", interest_accrual=2200.00)
		rec_d5 = reconcile_fund(self.fund_a_code, "2026-11-06")
		self.assertTrue(rec_d5["within_tolerance"], f"Day 5 failed: {rec_d5}")

		_cols, rows = run_recon_report(
			{
				"fund": self.fund_a_code,
				"from_date": "2026-11-02",
				"to_date": "2026-11-06",
			}
		)
		self.assertEqual(len(rows), 5)
		for r in rows:
			self.assertEqual(r["within_tolerance"], 1)
			self.assertEqual(r["status"], "Reconciled")

		report_doc = frappe.get_doc("Report", "Fund NAV Reconciliation")
		report_roles = [r.role for r in report_doc.roles]
		self.assertIn("Asset Compliance Officer", report_roles)

		# Tamper test: Post manual Journal Entry to the fund's investment account on Day 5
		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.company = self.fund_a_doc.company
		je.posting_date = "2026-11-06"
		je.user_remark = "R12_TAMPER_TEST manual adjustment to investment account"
		je.append(
			"accounts",
			{
				"account": self.fund_a_doc.investment_revaluation_account,
				"debit_in_account_currency": 75000.00,
				"credit_in_account_currency": 0.00,
			},
		)
		je.append(
			"accounts",
			{
				"account": self.fund_a_doc.unrealised_gain_loss_account,
				"debit_in_account_currency": 0.00,
				"credit_in_account_currency": 75000.00,
			},
		)
		# Test setup: ignore_permissions required
		je.insert(ignore_permissions=True)
		je.submit()

		rec_d5_tampered = reconcile_fund(self.fund_a_code, "2026-11-06")
		self.assertFalse(rec_d5_tampered["within_tolerance"])
		self.assertAlmostEqual(float(rec_d5_tampered["difference"]), -75000.00, places=1)

		_, rows_after = run_recon_report(
			{
				"fund": self.fund_a_code,
				"from_date": "2026-11-02",
				"to_date": "2026-11-06",
			}
		)
		self.assertEqual(rows_after[-1]["within_tolerance"], 0)
		self.assertEqual(rows_after[-1]["status"], "Failed")

		val_d6 = frappe.new_doc("Asset Fund Valuation")
		val_d6.fund = self.fund_a_code
		val_d6.valuation_date = "2026-11-09"
		val_d6.daily_interest_accrual = 1000.00
		val_d6.prepared_by = "Administrator"
		val_d6.approved_by = self.checker
		# Test setup: ignore_permissions required
		val_d6.insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError) as ctx:
			val_d6.submit()
		self.assertIn("75,000", str(ctx.exception))
