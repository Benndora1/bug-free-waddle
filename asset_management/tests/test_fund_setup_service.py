"""Integration tests for one-click fund company & COA provisioning (services/fund_setup.py)."""

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.services.fund_setup import (
	seed_default_account_templates,
	setup_fund_accounts,
)


class TestFundSetupService(IntegrationTestCase):
	def setUp(self) -> None:
		super().setUp()
		frappe.set_user("Administrator")
		seed_default_account_templates(backfill_existing=False)
		self.fund_id = "TEST-SETUP-01"
		self.company_name = "Test Setup Fund 01"

	def test_01_active_fund_without_accounts_blocked(self) -> None:
		"""Active fund without all 17 accounts configured must fail with a clear validation error."""
		fund = frappe.new_doc("Asset Fund")
		fund.fund_id = self.fund_id
		fund.fund_name = self.company_name
		fund.fund_type = "Money Market Fund"
		fund.currency = "USD"
		fund.launch_date = frappe.utils.nowdate()
		fund.status = "Active"

		with self.assertRaises(frappe.ValidationError) as ctx:
			fund.insert(ignore_permissions=True)

		self.assertIn("cannot become Active until all accounting fields are configured", str(ctx.exception))

	def test_02_setup_fund_accounts_creates_company_accounts_and_is_idempotent(self) -> None:
		"""setup_fund_accounts provisions Company, 17 template accounts, Unit Holders mapping, and is idempotent."""
		fund = frappe.new_doc("Asset Fund")
		fund.fund_id = self.fund_id
		fund.fund_name = self.company_name
		fund.fund_type = "Money Market Fund"
		fund.currency = "USD"
		fund.launch_date = frappe.utils.nowdate()
		fund.company = None
		fund.status = "Suspended"
		# Test setup: ignore_permissions required
		fund.insert(ignore_permissions=True)

		setup_fund_accounts(self.fund_id)
		fund.reload()

		self.assertTrue(fund.company, "Fund company was not set")
		self.assertTrue(frappe.db.exists("Company", fund.company))
		comp = frappe.get_doc("Company", fund.company)
		self.assertEqual(comp.default_currency, "USD")

		expected_keys = [
			"client_cash_payable_account",
			"unallocated_receipts_account",
			"unitholders_capital_account",
			"entry_fee_payable_account",
			"exit_fee_payable_account",
			"wht_payable_account",
			"fees_payable_account",
			"due_to_other_funds_account",
			"due_from_other_funds_account",
			"interest_receivable_account",
			"investments_at_cost_account",
			"investment_revaluation_account",
			"interest_income_account",
			"unrealised_gain_loss_account",
			"realised_gain_loss_account",
			"fund_expenses_account",
			"rounding_account",
		]

		for key in expected_keys:
			acc_name = getattr(fund, key, None)
			self.assertTrue(acc_name, f"Account field {key} is empty on Asset Fund")
			self.assertTrue(frappe.db.exists("Account", acc_name))
			acc_company = frappe.db.get_value("Account", acc_name, "company")
			self.assertEqual(acc_company, fund.company)

		sg = frappe.get_doc("Supplier Group", "Unit Holders")
		matching_rows = [r for r in sg.accounts if r.company == fund.company]
		self.assertEqual(len(matching_rows), 1)
		self.assertEqual(matching_rows[0].account, fund.client_cash_payable_account)

		fund.status = "Active"
		# Test setup: ignore_permissions required
		fund.save(ignore_permissions=True)
		self.assertEqual(fund.status, "Active")

		# Idempotency check on second run
		initial_company = fund.company
		initial_accounts = {k: getattr(fund, k) for k in expected_keys}
		total_accounts_before = frappe.db.count("Account", {"company": initial_company})

		setup_fund_accounts(self.fund_id)
		fund.reload()
		total_accounts_after = frappe.db.count("Account", {"company": initial_company})

		self.assertEqual(total_accounts_before, total_accounts_after)
		self.assertEqual(fund.company, initial_company)
		for k, v in initial_accounts.items():
			self.assertEqual(getattr(fund, k), v)
