import unittest

import frappe
from frappe import _

from asset_management.services.fund_setup import setup_fund_accounts


class TestFundSetupService(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		# Ensure clean test state for test fund and test company
		cls.fund_id = "TEST-SETUP-01"
		cls.company_name = "Test Setup Fund 01"

		if frappe.db.exists("Asset Fund", cls.fund_id):
			frappe.delete_doc("Asset Fund", cls.fund_id, force=True, ignore_permissions=True)
		if frappe.db.exists("Company", cls.company_name):
			frappe.delete_doc("Company", cls.company_name, force=True, ignore_permissions=True)

		# Ensure default template rows exist in Fund Management Settings
		from asset_management.services.fund_setup import seed_default_account_templates

		seed_default_account_templates()

	@classmethod
	def tearDownClass(cls):
		if frappe.db.exists("Asset Fund", cls.fund_id):
			frappe.delete_doc("Asset Fund", cls.fund_id, force=True, ignore_permissions=True)
		if frappe.db.exists("Company", cls.company_name):
			frappe.delete_doc("Company", cls.company_name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_01_active_fund_without_accounts_blocked(self):
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

	def test_02_setup_fund_accounts_creates_company_accounts_and_supplier_group(self):
		"""setup_fund_accounts provisions Company, 17 template accounts, and Unit Holders mapping."""
		fund = frappe.new_doc("Asset Fund")
		fund.fund_id = self.fund_id
		fund.fund_name = self.company_name
		fund.fund_type = "Money Market Fund"
		fund.currency = "USD"
		fund.launch_date = frappe.utils.nowdate()
		fund.company = None
		fund.status = "Suspended"
		fund.insert(ignore_permissions=True)

		# Execute setup
		setup_fund_accounts(self.fund_id)

		fund.reload()
		self.assertTrue(fund.company, "Fund company was not set")
		self.assertTrue(frappe.db.exists("Company", fund.company), f"Company {fund.company} does not exist")

		comp = frappe.get_doc("Company", fund.company)
		self.assertEqual(comp.default_currency, "USD")

		# Check all 17 account fields
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
			self.assertTrue(frappe.db.exists("Account", acc_name), f"Account {acc_name} does not exist in DB")
			acc_company = frappe.db.get_value("Account", acc_name, "company")
			self.assertEqual(
				acc_company,
				fund.company,
				f"Account {acc_name} belongs to {acc_company}, expected {fund.company}",
			)

		# Check Supplier Group 'Unit Holders' Party Account
		sg = frappe.get_doc("Supplier Group", "Unit Holders")
		matching_rows = [r for r in sg.accounts if r.company == fund.company]
		self.assertEqual(len(matching_rows), 1, "Expected exactly 1 party account row for fund company")
		self.assertEqual(matching_rows[0].account, fund.client_cash_payable_account)

		# Activating fund now succeeds
		fund.status = "Active"
		fund.save(ignore_permissions=True)
		self.assertEqual(fund.status, "Active")

	def test_03_setup_fund_accounts_is_idempotent(self):
		"""Second run of setup_fund_accounts must create 0 new records and alter nothing."""
		fund = frappe.get_doc("Asset Fund", self.fund_id)
		setup_fund_accounts(self.fund_id)
		fund.reload()

		initial_company = fund.company
		initial_accounts = {
			k: getattr(fund, k)
			for k in [
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
		}

		total_accounts_before = frappe.db.count("Account", {"company": initial_company})

		# Run setup a second time
		setup_fund_accounts(self.fund_id)

		fund.reload()
		total_accounts_after = frappe.db.count("Account", {"company": initial_company})

		self.assertEqual(
			total_accounts_before, total_accounts_after, "New accounts were unexpectedly created"
		)
		self.assertEqual(fund.company, initial_company)

		for k, v in initial_accounts.items():
			self.assertEqual(getattr(fund, k), v, f"Account field {k} changed on second run")

		sg = frappe.get_doc("Supplier Group", "Unit Holders")
		matching_rows = [r for r in sg.accounts if r.company == initial_company]
		self.assertEqual(len(matching_rows), 1, "Duplicate party account rows created in Unit Holders")
