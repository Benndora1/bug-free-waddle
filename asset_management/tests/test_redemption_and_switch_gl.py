"""Integration tests for Asset Redemption and Asset Fund Switch GL posting and unit ledger (Task R-10)."""

from decimal import Decimal
from types import SimpleNamespace

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from asset_management.services.units import (
	get_active_lien_units,
	get_unit_balance,
	make_unit_ledger_entry,
	rebuild_portfolio,
)
from asset_management.tests.factories import (
	make_approved_valuation,
	make_checker_user,
	make_fund,
	make_investor,
)


class TestRedemptionAndSwitchGL(IntegrationTestCase):
	def setUp(self) -> None:
		super().setUp()
		frappe.set_user("Administrator")
		self.checker = make_checker_user()
		self.dealing_date = "2026-11-12"

		self.inv_doc = make_investor(investor_name="R10 Test Investor")
		self.investor_id = self.inv_doc.name
		self.supplier = self.inv_doc.supplier

		self.fund_a_doc = make_fund(
			fund_id="TEST-FUND-R10-A",
			fund_name="R10 Test Fund A",
			fund_type="Money Market Fund",
			nav=120.500000,
			bid=120.500000,
			offer=120.500000,
			price_date=self.dealing_date,
			exit_fee_pct=0.5,
			entry_fee_pct=0.0,
			wht_basis="None",
			wht_rate=0.0,
			min_balance_amount=0.0,
		)
		self.fund_a_code = self.fund_a_doc.name

		self.fund_b_doc = make_fund(
			fund_id="TEST-FUND-R10-B",
			fund_name="R10 Test Fund B",
			fund_type="Balanced Fund",
			nav=50.250000,
			bid=50.250000,
			offer=50.250000,
			price_date=self.dealing_date,
			exit_fee_pct=0.0,
			entry_fee_pct=0.0,
			wht_basis="None",
			wht_rate=0.0,
			min_balance_amount=0.0,
		)
		self.fund_b_code = self.fund_b_doc.name

		make_approved_valuation(
			self.fund_a_code, date=self.dealing_date, nav=120.500000, bid=120.500000, offer=120.500000
		)
		make_approved_valuation(
			self.fund_b_code, date=self.dealing_date, nav=50.250000, bid=50.250000, offer=50.250000
		)

		seed_voucher = SimpleNamespace(
			doctype="Asset Subscription",
			name="__TEST_SUB_R10_SEED",
			transaction_date="2026-11-01",
		)
		make_unit_ledger_entry(
			seed_voucher,
			[
				{
					"posting_date": "2026-11-01",
					"investor": self.investor_id,
					"fund": self.fund_a_code,
					"entry_type": "Subscription",
					"units": Decimal("10000.000000"),
					"price_per_unit": Decimal("100.000000"),
					"amount": Decimal("1000000.00"),
				}
			],
		)
		rebuild_portfolio(self.investor_id, self.fund_a_code)

	def test_01_redemption_gl_unit_ledger_and_cancel(self) -> None:
		"""Holding 10,000 units, redeem 4,000 at bid 120.500000, exit fee 0.5%, WHT None ->
		gross 482,000.00, exit fee 2,410.00, net 479,590.00, 3 GL rows, balance 6,000.000000.
		Cancel restores 10,000.000000 units and nets GL to zero.
		"""
		self.assertEqual(
			get_unit_balance(self.investor_id, self.fund_a_code, self.dealing_date),
			Decimal("10000.000000"),
		)

		red = frappe.new_doc("Asset Redemption")
		red.investor = self.investor_id
		red.fund = self.fund_a_code
		red.redemption_date = self.dealing_date
		red.received_at = "10:00:00"
		red.redemption_by = "Units"
		red.requested_units = 4000.0
		red.exit_fee_pct = 0.5
		red.prior_day_valuation_approved = 1
		red.maker = "Administrator"
		red.checker = self.checker
		# Test setup: ignore_permissions required
		red.insert(ignore_permissions=True)

		self.assertEqual(flt(red.gross_redemption_amount, 2), 482000.00)
		self.assertEqual(flt(red.exit_fee_amount, 2), 2410.00)
		self.assertEqual(flt(red.withholding_tax_amount, 2), 0.00)
		self.assertEqual(flt(red.net_payout_amount, 2), 479590.00)

		red.checker_approved = 1
		red.workflow_state = "Approved"
		red.submit()

		gl_rows = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Asset Redemption", "voucher_no": red.name, "is_cancelled": 0},
			fields=["account", "debit", "credit", "party_type", "party", "company"],
		)
		self.assertEqual(len(gl_rows), 3)
		for row in gl_rows:
			self.assertEqual(row.company, self.fund_a_doc.company)

		by_account = {r.account: r for r in gl_rows}
		self.assertEqual(flt(by_account[self.fund_a_doc.unitholders_capital_account].debit, 2), 482000.00)
		self.assertEqual(flt(by_account[self.fund_a_doc.client_cash_payable_account].credit, 2), 479590.00)
		self.assertEqual(by_account[self.fund_a_doc.client_cash_payable_account].party_type, "Supplier")
		self.assertEqual(by_account[self.fund_a_doc.client_cash_payable_account].party, self.supplier)
		self.assertEqual(flt(by_account[self.fund_a_doc.exit_fee_payable_account].credit, 2), 2410.00)

		self.assertEqual(
			get_unit_balance(self.investor_id, self.fund_a_code, self.dealing_date),
			Decimal("6000.000000"),
		)
		reg_lines = frappe.get_all("Asset Investor Register Line", filters={"voucher_no": red.name})
		self.assertEqual(len(reg_lines), 0)

		red.reload()
		red.cancel()

		self.assertEqual(
			get_unit_balance(self.investor_id, self.fund_a_code, self.dealing_date),
			Decimal("10000.000000"),
		)
		all_gl = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Asset Redemption", "voucher_no": red.name},
			fields=["debit", "credit"],
		)
		total_dr = sum(Decimal(str(r.debit)) for r in all_gl)
		total_cr = sum(Decimal(str(r.credit)) for r in all_gl)
		self.assertEqual(total_dr - total_cr, Decimal("0.00"))
		active_gl = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Asset Redemption", "voucher_no": red.name, "is_cancelled": 0},
		)
		self.assertEqual(len(active_gl), 0)

	def test_02_over_redemption_and_lien_blocking(self) -> None:
		"""Redeeming 10,000.000001 units fails. A lien of 7,000 units blocks redeeming 4,000 units."""
		red_over = frappe.new_doc("Asset Redemption")
		red_over.investor = self.investor_id
		red_over.fund = self.fund_a_code
		red_over.redemption_date = self.dealing_date
		red_over.received_at = "10:00:00"
		red_over.redemption_by = "Units"
		red_over.requested_units = 10000.000001
		red_over.prior_day_valuation_approved = 1
		with self.assertRaises(frappe.ValidationError):
			red_over.insert(ignore_permissions=True)

		lien_voucher = SimpleNamespace(
			doctype="Asset Subscription",
			name="__TEST_LIEN_R10_01",
			transaction_date=self.dealing_date,
		)
		make_unit_ledger_entry(
			lien_voucher,
			[
				{
					"posting_date": self.dealing_date,
					"investor": self.investor_id,
					"fund": self.fund_a_code,
					"entry_type": "Lien",
					"units": Decimal("7000.000000"),
					"price_per_unit": Decimal("120.500000"),
					"amount": Decimal("843500.00"),
				}
			],
		)
		self.assertEqual(
			get_active_lien_units(self.investor_id, self.fund_a_code, self.dealing_date),
			Decimal("7000.000000"),
		)
		red_lien = frappe.new_doc("Asset Redemption")
		red_lien.investor = self.investor_id
		red_lien.fund = self.fund_a_code
		red_lien.redemption_date = self.dealing_date
		red_lien.received_at = "10:00:00"
		red_lien.redemption_by = "Units"
		red_lien.requested_units = 4000.0
		red_lien.prior_day_valuation_approved = 1
		with self.assertRaises(frappe.ValidationError):
			red_lien.insert(ignore_permissions=True)

	def test_03_switch_gl_unit_ledger_and_cancel(self) -> None:
		"""Switch 1,000 units A (bid 120.500000) -> B (offer 50.250000), no fees ->
		120,500.00 moved, 2398.009950 units in B, GL balanced in both companies, cancel reverses both.
		"""
		swi = frappe.new_doc("Asset Fund Switch")
		swi.investor = self.investor_id
		swi.from_fund = self.fund_a_code
		swi.to_fund = self.fund_b_code
		swi.switch_date = self.dealing_date
		swi.received_at = "10:00:00"
		swi.switch_by = "Units"
		swi.switch_units = 1000.0
		swi.switch_fee_pct = 0.0
		swi.entry_fee_pct = 0.0
		swi.maker = "Administrator"
		swi.checker = self.checker
		# Test setup: ignore_permissions required
		swi.insert(ignore_permissions=True)

		self.assertEqual(flt(swi.gross_switch_amount, 2), 120500.00)
		self.assertEqual(flt(swi.switch_fee_amount, 2), 0.00)
		self.assertEqual(flt(swi.net_switch_amount, 2), 120500.00)
		self.assertEqual(flt(swi.entry_fee_amount, 2), 0.00)
		self.assertAlmostEqual(flt(swi.units_allocated_to_fund, 6), 2398.009950, places=6)

		swi.approved_by_checker = 1
		swi.workflow_state = "Approved"
		swi.submit()

		self.assertEqual(
			get_unit_balance(self.investor_id, self.fund_a_code, self.dealing_date),
			Decimal("9000.000000"),
		)
		self.assertEqual(
			get_unit_balance(self.investor_id, self.fund_b_code, self.dealing_date),
			Decimal("2398.009950"),
		)

		gl_a = frappe.get_all(
			"GL Entry",
			filters={
				"voucher_type": "Asset Fund Switch",
				"voucher_no": swi.name,
				"company": self.fund_a_doc.company,
				"is_cancelled": 0,
			},
			fields=["account", "debit", "credit"],
		)
		self.assertEqual(len(gl_a), 2)
		by_acc_a = {r.account: r for r in gl_a}
		self.assertEqual(flt(by_acc_a[self.fund_a_doc.unitholders_capital_account].debit, 2), 120500.00)
		self.assertEqual(flt(by_acc_a[self.fund_a_doc.due_to_other_funds_account].credit, 2), 120500.00)

		gl_b = frappe.get_all(
			"GL Entry",
			filters={
				"voucher_type": "Asset Fund Switch",
				"voucher_no": swi.name,
				"company": self.fund_b_doc.company,
				"is_cancelled": 0,
			},
			fields=["account", "debit", "credit"],
		)
		self.assertEqual(len(gl_b), 2)
		by_acc_b = {r.account: r for r in gl_b}
		self.assertEqual(flt(by_acc_b[self.fund_b_doc.due_from_other_funds_account].debit, 2), 120500.00)
		self.assertEqual(flt(by_acc_b[self.fund_b_doc.unitholders_capital_account].credit, 2), 120500.00)

		reg_lines = frappe.get_all("Asset Investor Register Line", filters={"voucher_no": swi.name})
		self.assertEqual(len(reg_lines), 0)

		swi.reload()
		swi.cancel()

		self.assertEqual(
			get_unit_balance(self.investor_id, self.fund_a_code, self.dealing_date),
			Decimal("10000.000000"),
		)
		self.assertEqual(
			get_unit_balance(self.investor_id, self.fund_b_code, self.dealing_date),
			Decimal("0.000000"),
		)
		active_gl = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Asset Fund Switch", "voucher_no": swi.name, "is_cancelled": 0},
		)
		self.assertEqual(len(active_gl), 0)

	def test_04_redemption_by_amount_and_pending_price_guard(self) -> None:
		"""Redemption by amount rounds units UP to 6 dp; post-cut-off dealing enters Pending Price and blocks submit."""
		red_amt = frappe.new_doc("Asset Redemption")
		red_amt.investor = self.investor_id
		red_amt.fund = self.fund_a_code
		red_amt.redemption_date = self.dealing_date
		red_amt.received_at = "10:00:00"
		red_amt.redemption_by = "Amount"
		red_amt.requested_amount = 100000.00
		red_amt.exit_fee_pct = 0.0
		red_amt.prior_day_valuation_approved = 1
		red_amt.maker = "Administrator"
		red_amt.checker = self.checker
		# Test setup: ignore_permissions required
		red_amt.insert(ignore_permissions=True)

		self.assertAlmostEqual(flt(red_amt.units_to_redeem, 6), 829.875519, places=6)

		red_pending = frappe.new_doc("Asset Redemption")
		red_pending.investor = self.investor_id
		red_pending.fund = self.fund_a_code
		red_pending.redemption_date = self.dealing_date
		red_pending.received_at = "16:00:00"
		red_pending.redemption_by = "Units"
		red_pending.requested_units = 1000.0
		red_pending.prior_day_valuation_approved = 1
		red_pending.maker = "Administrator"
		red_pending.checker = self.checker
		# Test setup: ignore_permissions required
		red_pending.insert(ignore_permissions=True)

		self.assertEqual(red_pending.status, "Pending Price")
		red_pending.checker_approved = 1
		red_pending.workflow_state = "Approved"
		with self.assertRaises(frappe.ValidationError):
			red_pending.submit()
