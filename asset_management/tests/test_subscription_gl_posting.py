"""Integration tests for Asset Subscription GL posting, pricing, and lifecycle (Task R-09)."""

import unittest
from decimal import Decimal

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import add_days, flt, nowdate

from asset_management.accounting.posting import get_accounting_settings
from asset_management.services.units import get_unit_balance


class TestSubscriptionGLPosting(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.investor = "__TEST_R09_INV_01"
		cls.fund = "SBG-MMF"
		cls.company = "SBG Securities Uganda"

		# Ensure investor exists
		if not frappe.db.exists("Asset Investor", cls.investor):
			inv = frappe.new_doc("Asset Investor")
			inv.investor_id = cls.investor
			inv.investor_name = "R09 Institutional Test Client"
			inv.investor_type = "Corporate"
			inv.email = "r09_test@example.com"
			inv.phone = "+256700000088"
			inv.status = "Active"
			inv.insert(ignore_permissions=True)

		# Ensure Fund Management Settings is configured
		settings = get_accounting_settings()
		if settings:
			settings.fund_manager_company = cls.company
			settings.default_fund_company = cls.company
			settings.client_cash_payable_account = "Client Cash Payable - SBGS"
			settings.unitholders_capital_account = "Unitholders Capital - SBGS"
			settings.entry_fee_payable_account = "Entry Fee Payable - SBGS"
			settings.rounding_account = "Rounding Adjustment - SBGS"
			settings.commission_expense_account = "Agent Commission Expense - SBGS"
			settings.commission_payable_account = "Agent Commission Payable - SBGS"
			settings.max_rounding_tolerance = 0.05
			settings.save()

		# Ensure Fund exists and is linked
		fund_doc = frappe.get_doc("Asset Fund", cls.fund)
		fund_doc.company = cls.company
		fund_doc.save(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		fund_doc = frappe.get_doc("Asset Fund", cls.fund)
		fund_doc.current_offer_price = 100.0
		fund_doc.current_bid_price = 100.0
		fund_doc.current_nav_per_unit = 100.0
		fund_doc.last_valuation_date = nowdate()
		fund_doc.save(ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		"""Clean prior test subscriptions and ledger entries."""
		frappe.set_user("Administrator")
		# Delete prior subscriptions and ledger entries for this test investor
		subs = frappe.get_all("Asset Subscription", filters={"investor": self.investor}, pluck="name")
		for s in subs:
			frappe.db.delete("GL Entry", {"voucher_type": "Asset Subscription", "voucher_no": s})
			frappe.db.delete(
				"Asset Unit Ledger Entry", {"voucher_type": "Asset Subscription", "voucher_no": s}
			)
			frappe.db.delete("Asset Investor Register Line", {"voucher_no": s})
			frappe.db.delete("Asset Subscription", {"name": s})

		frappe.db.delete("Asset Unit Ledger Entry", {"investor": self.investor})
		portfolio_id = f"{self.investor}-{self.fund}"
		if frappe.db.exists("Asset Investor Portfolio", portfolio_id):
			frappe.db.delete("Asset Investor Portfolio", {"name": portfolio_id})
		frappe.db.commit()

	def test_01_pending_price_blocks_submission(self):
		"""Verify that a subscription on a dealing date without a published price enters

		'Pending Price' status and cannot be submitted.
		"""
		# Dealing date in the future where no price has been published yet
		future_date = add_days(nowdate(), 30)

		sub = frappe.new_doc("Asset Subscription")
		sub.investor = self.investor
		sub.fund = self.fund
		sub.subscription_date = future_date
		sub.gross_amount = 10000000.0
		sub.entry_fee_pct = 1.0
		sub.insert(ignore_permissions=True)

		# Must be in Pending Price status
		self.assertEqual(sub.status, "Pending Price")
		self.assertEqual(sub.applicable_nav_price, 0.0)
		self.assertEqual(sub.units_allocated, 0.0)

		# Submission must fail with clear validation error
		sub.workflow_state = "Approved"
		sub.approved_by_operations = 1
		with self.assertRaises(frappe.ValidationError):
			sub.submit()

	def test_02_subscription_posting_exact_numbers_and_gl_lifecycle(self):
		"""Verify exact pricing calculations, 3-row GL posting, and cancellation lifecycle:

		Gross 10,000,000.00, Fee 1%, Offer 115.452000 ->
		- Fee = 100,000.00
		- Net = 9,900,000.00
		- Units = 85749.922045
		- GL: 3 rows balancing to 0
		- Cancel: GL net zero, unit balance unchanged
		"""
		# 1. Publish exact price on fund
		fund_doc = frappe.get_doc("Asset Fund", self.fund)
		fund_doc.current_offer_price = 115.452000
		fund_doc.last_valuation_date = nowdate()
		fund_doc.save(ignore_permissions=True)

		initial_unit_balance = get_unit_balance(self.investor, self.fund)
		self.assertEqual(initial_unit_balance, Decimal("0.000000"))

		# 2. Create subscription
		sub = frappe.new_doc("Asset Subscription")
		sub.investor = self.investor
		sub.fund = self.fund
		sub.subscription_date = nowdate()
		sub.gross_amount = 10000000.00
		sub.entry_fee_pct = 1.0
		sub.maker = "Administrator"
		sub.checker = "test_checker@example.com"
		sub.insert(ignore_permissions=True)

		# 3. Assert exact calculation results
		self.assertEqual(flt(sub.applicable_nav_price, 6), 115.452000)
		self.assertEqual(flt(sub.entry_fee_amount, 2), 100000.00)
		self.assertEqual(flt(sub.net_invested_amount, 2), 9900000.00)
		self.assertEqual(flt(sub.units_allocated, 6), 85749.922045)
		self.assertEqual(sub.status, "Draft")

		# 4. Approve & Submit
		sub.approved_by_operations = 1
		sub.workflow_state = "Approved"
		sub.submit()

		self.assertEqual(sub.status, "Submitted")

		# 5. Verify Unit Ledger balance
		bal_after_sub = get_unit_balance(self.investor, self.fund)
		self.assertEqual(bal_after_sub, Decimal("85749.922045"))

		# 6. Verify GL Entries: Exactly 3 rows for Fund Company that balance to 0
		gl_entries = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Asset Subscription", "voucher_no": sub.name, "company": self.company},
			fields=["account", "debit", "credit", "party_type", "party", "is_cancelled"],
			order_by="creation asc",
		)

		self.assertEqual(len(gl_entries), 3)

		total_debit = sum(Decimal(str(e.debit)) for e in gl_entries)
		total_credit = sum(Decimal(str(e.credit)) for e in gl_entries)
		self.assertEqual(total_debit, Decimal("10000000.00"))
		self.assertEqual(total_credit, Decimal("10000000.00"))
		self.assertEqual(total_debit - total_credit, Decimal("0.00"))

		# Check row details:
		# Row 1: Client Cash Payable (party_type Supplier) gross debit
		cash_entry = next(e for e in gl_entries if e.account == "Client Cash Payable - SBGS")
		self.assertEqual(Decimal(str(cash_entry.debit)), Decimal("10000000.00"))
		self.assertEqual(Decimal(str(cash_entry.credit)), Decimal("0.00"))
		self.assertEqual(cash_entry.party_type, "Supplier")
		self.assertTrue(bool(cash_entry.party))

		# Row 2: Unitholders Capital net credit
		capital_entry = next(e for e in gl_entries if e.account == "Unitholders Capital - SBGS")
		self.assertEqual(Decimal(str(capital_entry.debit)), Decimal("0.00"))
		self.assertEqual(Decimal(str(capital_entry.credit)), Decimal("9900000.00"))

		# Row 3: Entry Fee Payable credit
		fee_entry = next(e for e in gl_entries if e.account == "Entry Fee Payable - SBGS")
		self.assertEqual(Decimal(str(fee_entry.debit)), Decimal("0.00"))
		self.assertEqual(Decimal(str(fee_entry.credit)), Decimal("100000.00"))

		# 7. Cancel Subscription
		sub.cancel()
		self.assertEqual(sub.status, "Cancelled")

		# 8. Assert Unit Ledger restored to initial (0.000000)
		bal_after_cancel = get_unit_balance(self.investor, self.fund)
		self.assertEqual(bal_after_cancel, Decimal("0.000000"))

		# 9. Assert GL Entries net zero for the voucher
		all_gl_entries = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Asset Subscription", "voucher_no": sub.name},
			fields=["debit", "credit", "is_cancelled"],
		)
		net_gl = sum(Decimal(str(e.debit)) - Decimal(str(e.credit)) for e in all_gl_entries)
		self.assertEqual(net_gl, Decimal("0.00"))

	def test_03_agent_commission_gl_posting_in_fund_manager_company(self):
		"""Verify that agent commission generates liability GL entries in the Fund Manager

		company and that cancellation marks the commission row Cancelled and reverses GL.
		"""
		# Ensure test agent exists
		agent_code = "AGT-R09-01"
		if not frappe.db.exists("Asset Agent", {"agent_code": agent_code}):
			ag = frappe.new_doc("Asset Agent")
			ag.agent_code = agent_code
			ag.agent_name = "R09 Test Brokerage Agent"
			ag.agent_type = "Corporate / Broker"
			ag.commission_rate_pct = 0.50
			ag.status = "Active"
			ag.insert(ignore_permissions=True)

		# Publish fund price
		fund_doc = frappe.get_doc("Asset Fund", self.fund)
		fund_doc.current_offer_price = 115.452000
		fund_doc.last_valuation_date = nowdate()
		fund_doc.save(ignore_permissions=True)

		# Create subscription with agent
		sub = frappe.new_doc("Asset Subscription")
		sub.investor = self.investor
		sub.fund = self.fund
		sub.subscription_date = nowdate()
		sub.gross_amount = 10000000.00
		sub.entry_fee_pct = 1.0
		sub.agent = agent_code
		sub.agent_commission_pct = 0.50  # 0.5% = 50,000.00
		sub.maker = "Administrator"
		sub.checker = "test_checker@example.com"
		sub.insert(ignore_permissions=True)

		self.assertEqual(flt(sub.agent_commission_amount, 2), 50000.00)

		# Approve & Submit
		sub.approved_by_operations = 1
		sub.workflow_state = "Approved"
		sub.submit()

		# Verify Fund Manager company GL entries: Commission Expense (Dr) & Commission Payable (Cr)
		fm_gl_entries = frappe.get_all(
			"GL Entry",
			filters={
				"voucher_type": "Asset Subscription",
				"voucher_no": sub.name,
				"account": ["in", ["Agent Commission Expense - SBGS", "Agent Commission Payable - SBGS"]],
			},
			fields=["account", "debit", "credit"],
		)
		self.assertEqual(len(fm_gl_entries), 2)
		exp_entry = next(e for e in fm_gl_entries if e.account == "Agent Commission Expense - SBGS")
		self.assertEqual(Decimal(str(exp_entry.debit)), Decimal("50000.00"))
		pay_entry = next(e for e in fm_gl_entries if e.account == "Agent Commission Payable - SBGS")
		self.assertEqual(Decimal(str(pay_entry.credit)), Decimal("50000.00"))

		# Verify Asset Agent Commission row
		comm = frappe.get_doc("Asset Agent Commission", {"subscription": sub.name})
		self.assertEqual(comm.payment_status, "Accrued")
		self.assertEqual(flt(comm.commission_amount, 2), 50000.00)

		# Cancel subscription
		sub.cancel()

		# Commission row should be Cancelled
		comm.reload()
		self.assertEqual(comm.payment_status, "Cancelled")

		# GL entries across all companies must balance to net zero
		all_gl_entries = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Asset Subscription", "voucher_no": sub.name},
			fields=["debit", "credit"],
		)
		net_gl = sum(Decimal(str(e.debit)) - Decimal(str(e.credit)) for e in all_gl_entries)
		self.assertEqual(net_gl, Decimal("0.00"))


if __name__ == "__main__":
	unittest.main()
