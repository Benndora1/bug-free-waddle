import unittest
from decimal import Decimal
from types import SimpleNamespace

import frappe
from frappe.utils import flt

from asset_management.services.fund_setup import seed_default_account_templates, setup_fund_accounts
from asset_management.services.units import (
	get_active_lien_units,
	get_unit_balance,
	make_unit_ledger_entry,
	rebuild_portfolio,
)


class TestRedemptionAndSwitchGL(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		frappe.set_user("Administrator")
		seed_default_account_templates()

		cls.investor_id = "__TEST_INV_R10_01"
		cls.fund_a_code = "__TEST_FUND_R10_A"
		cls.fund_b_code = "__TEST_FUND_R10_B"
		cls.dealing_date = "2026-11-12"

		cls._cleanup()

		# Ensure test checker user exists
		if not frappe.db.exists("User", "test_checker@example.com"):
			u = frappe.new_doc("User")
			u.email = "test_checker@example.com"
			u.first_name = "Test"
			u.last_name = "Checker"
			u.send_welcome_email = 0
			u.insert(ignore_permissions=True)

		# Create Investor (auto-links Supplier in "Unit Holders")
		inv = frappe.new_doc("Asset Investor")
		inv.investor_id = cls.investor_id
		inv.investor_name = "R10 Test Investor"
		inv.investor_type = "Individual"
		inv.identification_type = "National ID"
		inv.tax_id = "CM990011223344"
		inv.phone = "+256772999000"
		inv.bank_name = "Stanbic Bank Uganda"
		inv.bank_branch = "Main Branch"
		inv.bank_account_name = "R10 Test Investor"
		inv.bank_account_no = "9030098765432"
		inv.status = "Active"
		inv.kyc_status = "Verified"
		inv.insert(ignore_permissions=True)
		inv.reload()
		cls.supplier = inv.supplier

		# Create Fund A (bid = 120.500000, exit_fee = 0.5%, wht_basis = None)
		fund_a = frappe.new_doc("Asset Fund")
		fund_a.fund_id = cls.fund_a_code
		fund_a.fund_name = "R10 Test Fund A"
		fund_a.fund_type = "Money Market Fund"
		fund_a.fund_currency = "UGX"
		fund_a.launch_date = "2026-01-01"
		fund_a.initial_unit_price = 100.0
		fund_a.current_nav_per_unit = 120.500000
		fund_a.current_bid_price = 120.500000
		fund_a.current_offer_price = 120.500000
		fund_a.exit_fee_pct = 0.5
		fund_a.entry_fee_pct = 0.0
		fund_a.wht_basis = "None"
		fund_a.wht_rate = 0.0
		fund_a.min_initial_subscription = 100000.0
		fund_a.min_topup_amount = 50000.0
		fund_a.min_balance_amount = 0.0
		fund_a.status = "Suspended"
		fund_a.insert(ignore_permissions=True)
		setup_fund_accounts(cls.fund_a_code)
		frappe.db.set_value("Asset Fund", cls.fund_a_code, "status", "Active")

		# Create Fund B (offer = 50.250000, no fees)
		fund_b = frappe.new_doc("Asset Fund")
		fund_b.fund_id = cls.fund_b_code
		fund_b.fund_name = "R10 Test Fund B"
		fund_b.fund_type = "Balanced Fund"
		fund_b.fund_currency = "UGX"
		fund_b.launch_date = "2026-01-01"
		fund_b.initial_unit_price = 50.0
		fund_b.current_nav_per_unit = 50.250000
		fund_b.current_bid_price = 50.250000
		fund_b.current_offer_price = 50.250000
		fund_b.exit_fee_pct = 0.0
		fund_b.entry_fee_pct = 0.0
		fund_b.wht_basis = "None"
		fund_b.wht_rate = 0.0
		fund_b.min_initial_subscription = 100000.0
		fund_b.min_topup_amount = 50000.0
		fund_b.min_balance_amount = 0.0
		fund_b.status = "Suspended"
		fund_b.insert(ignore_permissions=True)
		setup_fund_accounts(cls.fund_b_code)
		frappe.db.set_value("Asset Fund", cls.fund_b_code, "status", "Active")

		# Publish Valuation records on 2026-11-12 for Fund A and Fund B so forward pricing resolves
		for fund_code, nav in [(cls.fund_a_code, 120.500000), (cls.fund_b_code, 50.250000)]:
			val = frappe.new_doc("Asset Fund Valuation")
			val.fund = fund_code
			val.valuation_date = cls.dealing_date
			val.cash_and_equivalents = 10000000.0
			val.total_units_in_issue = 100000.0
			val.nav_per_unit = nav
			val.insert(ignore_permissions=True)
			frappe.db.set_value(
				"Asset Fund Valuation",
				val.name,
				{"docstatus": 1, "status": "Approved", "nav_per_unit": nav},
			)

		# Give investor 10,000.000000 initial units in Fund A at 100.000000 (cost 1,000,000.00)
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
					"investor": cls.investor_id,
					"fund": cls.fund_a_code,
					"entry_type": "Subscription",
					"units": Decimal("10000.000000"),
					"price_per_unit": Decimal("100.000000"),
					"amount": Decimal("1000000.00"),
				}
			],
		)
		rebuild_portfolio(cls.investor_id, cls.fund_a_code)

	@classmethod
	def tearDownClass(cls) -> None:
		cls._cleanup()

	@classmethod
	def _cleanup(cls) -> None:
		for dt in ["Asset Redemption", "Asset Fund Switch"]:
			filters = {"investor": cls.investor_id} if dt in ("Asset Redemption", "Asset Fund Switch") else {}
			for name in frappe.get_all(dt, filters=filters, pluck="name"):
				frappe.db.delete("GL Entry", {"voucher_type": dt, "voucher_no": name})
				frappe.db.delete(dt, {"name": name})

		for name in frappe.get_all(
			"Asset Unit Ledger Entry", filters={"investor": cls.investor_id}, pluck="name"
		):
			frappe.db.delete("Asset Unit Ledger Entry", {"name": name})

		for name in frappe.get_all(
			"Asset Investor Portfolio", filters={"investor": cls.investor_id}, pluck="name"
		):
			frappe.db.delete("Asset Investor Portfolio", {"name": name})

		for name in frappe.get_all(
			"Asset Fund Valuation",
			filters={"fund": ["in", [cls.fund_a_code, cls.fund_b_code]]},
			pluck="name",
		):
			frappe.db.delete("Asset Fund Valuation", {"name": name})

		for fund_code in [cls.fund_a_code, cls.fund_b_code]:
			if frappe.db.exists("Asset Fund", fund_code):
				frappe.db.delete("Asset Fund", {"name": fund_code})

		if frappe.db.exists("Asset Investor", cls.investor_id):
			frappe.db.delete("Asset Investor", {"name": cls.investor_id})

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
		red.checker = "test_checker@example.com"
		red.insert(ignore_permissions=True)

		self.assertEqual(flt(red.gross_redemption_amount, 2), 482000.00)
		self.assertEqual(flt(red.exit_fee_amount, 2), 2410.00)
		self.assertEqual(flt(red.withholding_tax_amount, 2), 0.00)
		self.assertEqual(flt(red.net_payout_amount, 2), 479590.00)

		red.checker_approved = 1
		red.workflow_state = "Approved"
		red.submit()

		# Verify 3 GL rows in Fund A's company
		fund_a_doc = frappe.get_doc("Asset Fund", self.fund_a_code)
		gl_rows = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Asset Redemption", "voucher_no": red.name, "is_cancelled": 0},
			fields=["account", "debit", "credit", "party_type", "party", "company"],
		)
		self.assertEqual(len(gl_rows), 3)
		for row in gl_rows:
			self.assertEqual(row.company, fund_a_doc.company)

		expected_supplier = frappe.db.get_value("Asset Investor", self.investor_id, "supplier")
		self.assertTrue(expected_supplier)
		by_account = {r.account: r for r in gl_rows}
		self.assertEqual(flt(by_account[fund_a_doc.unitholders_capital_account].debit, 2), 482000.00)
		self.assertEqual(flt(by_account[fund_a_doc.client_cash_payable_account].credit, 2), 479590.00)
		self.assertEqual(by_account[fund_a_doc.client_cash_payable_account].party_type, "Supplier")
		self.assertEqual(by_account[fund_a_doc.client_cash_payable_account].party, expected_supplier)
		self.assertEqual(flt(by_account[fund_a_doc.exit_fee_payable_account].credit, 2), 2410.00)

		# Verify Unit Balance is 6,000.000000 and no Register Line exists
		self.assertEqual(
			get_unit_balance(self.investor_id, self.fund_a_code, self.dealing_date),
			Decimal("6000.000000"),
		)
		reg_lines = frappe.get_all("Asset Investor Register Line", filters={"voucher_no": red.name})
		self.assertEqual(len(reg_lines), 0)

		# Cancel restores 10,000.000000 units and nets GL to zero
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
		# 1. Over-redemption by 0.000001 units
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

		# 2. Active lien of 7,000 units leaves 3,000 available -> blocks redeeming 4,000 units
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
		try:
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
		finally:
			frappe.db.delete("Asset Unit Ledger Entry", {"voucher_no": "__TEST_LIEN_R10_01"})

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
		swi.checker = "test_checker@example.com"
		swi.insert(ignore_permissions=True)

		self.assertEqual(flt(swi.gross_switch_amount, 2), 120500.00)
		self.assertEqual(flt(swi.switch_fee_amount, 2), 0.00)
		self.assertEqual(flt(swi.net_switch_amount, 2), 120500.00)
		self.assertEqual(flt(swi.entry_fee_amount, 2), 0.00)
		self.assertAlmostEqual(flt(swi.units_allocated_to_fund, 6), 2398.009950, places=6)

		swi.approved_by_checker = 1
		swi.workflow_state = "Approved"
		swi.submit()

		# Check unit balances in both funds
		self.assertEqual(
			get_unit_balance(self.investor_id, self.fund_a_code, self.dealing_date),
			Decimal("9000.000000"),
		)
		self.assertEqual(
			get_unit_balance(self.investor_id, self.fund_b_code, self.dealing_date),
			Decimal("2398.009950"),
		)

		# Verify GL balanced in both Fund A company and Fund B company
		fund_a_doc = frappe.get_doc("Asset Fund", self.fund_a_code)
		fund_b_doc = frappe.get_doc("Asset Fund", self.fund_b_code)

		gl_a = frappe.get_all(
			"GL Entry",
			filters={
				"voucher_type": "Asset Fund Switch",
				"voucher_no": swi.name,
				"company": fund_a_doc.company,
				"is_cancelled": 0,
			},
			fields=["account", "debit", "credit"],
		)
		self.assertEqual(len(gl_a), 2)
		by_acc_a = {r.account: r for r in gl_a}
		self.assertEqual(flt(by_acc_a[fund_a_doc.unitholders_capital_account].debit, 2), 120500.00)
		self.assertEqual(flt(by_acc_a[fund_a_doc.due_to_other_funds_account].credit, 2), 120500.00)

		gl_b = frappe.get_all(
			"GL Entry",
			filters={
				"voucher_type": "Asset Fund Switch",
				"voucher_no": swi.name,
				"company": fund_b_doc.company,
				"is_cancelled": 0,
			},
			fields=["account", "debit", "credit"],
		)
		self.assertEqual(len(gl_b), 2)
		by_acc_b = {r.account: r for r in gl_b}
		self.assertEqual(flt(by_acc_b[fund_b_doc.due_from_other_funds_account].debit, 2), 120500.00)
		self.assertEqual(flt(by_acc_b[fund_b_doc.unitholders_capital_account].credit, 2), 120500.00)

		# Verify no Register Line created
		reg_lines = frappe.get_all("Asset Investor Register Line", filters={"voucher_no": swi.name})
		self.assertEqual(len(reg_lines), 0)

		# Cancel reverses both companies and both unit ledgers
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
		# 1. Redemption by Amount: 100,000.00 / 120.500000 = 829.87551867... -> 829.875519 (ROUND_UP)
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
		red_amt.checker = "test_checker@example.com"
		red_amt.insert(ignore_permissions=True)

		self.assertAlmostEqual(flt(red_amt.units_to_redeem, 6), 829.875519, places=6)
		frappe.db.delete("Asset Redemption", {"name": red_amt.name})

		# 2. Post-cut-off (16:00:00 > 15:00:00 cut-off) rolls to 2026-11-13 which has no valuation -> Pending Price
		red_pending = frappe.new_doc("Asset Redemption")
		red_pending.investor = self.investor_id
		red_pending.fund = self.fund_a_code
		red_pending.redemption_date = self.dealing_date
		red_pending.received_at = "16:00:00"
		red_pending.redemption_by = "Units"
		red_pending.requested_units = 1000.0
		red_pending.prior_day_valuation_approved = 1
		red_pending.maker = "Administrator"
		red_pending.checker = "test_checker@example.com"
		red_pending.insert(ignore_permissions=True)

		self.assertEqual(red_pending.status, "Pending Price")
		red_pending.checker_approved = 1
		red_pending.workflow_state = "Approved"
		with self.assertRaises(frappe.ValidationError):
			red_pending.submit()
		frappe.db.delete("Asset Redemption", {"name": red_pending.name})
