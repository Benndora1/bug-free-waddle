"""Integration tests for Asset Subscription GL posting, pricing, and lifecycle (Task R-09)."""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from asset_management.services.units import get_unit_balance
from asset_management.tests.factories import (
	make_agent,
	make_approved_valuation,
	make_checker_user,
	make_fund,
	make_fund_manager_company,
	make_investor,
)


class TestSubscriptionGLPosting(IntegrationTestCase):
	def setUp(self) -> None:
		super().setUp()
		frappe.set_user("Administrator")
		self.checker = make_checker_user()
		self.fm_company = make_fund_manager_company("Test Fund Manager")
		self.fund_doc = make_fund(
			fund_id="TEST-R09-MMF",
			fund_name="R09 Institutional MMF",
			nav=115.452000,
			bid=115.452000,
			offer=115.452000,
			price_date=nowdate(),
		)
		self.fund = self.fund_doc.name
		self.company = self.fund_doc.company
		self.inv_doc = make_investor(
			investor_name="R09 Institutional Test Client",
			investor_type="Corporate",
		)
		self.investor = self.inv_doc.name

	def test_01_pending_price_blocks_submission(self) -> None:
		"""Verify that a subscription on a dealing date without a published price enters
		'Pending Price' status and cannot be submitted.
		"""
		future_date = add_days(nowdate(), 30)

		sub = frappe.new_doc("Asset Subscription")
		sub.investor = self.investor
		sub.fund = self.fund
		sub.subscription_date = future_date
		sub.gross_amount = 10000000.0
		sub.entry_fee_pct = 1.0
		# Test setup: ignore_permissions required
		sub.insert(ignore_permissions=True)

		self.assertEqual(sub.status, "Pending Price")
		self.assertEqual(sub.applicable_nav_price, 0.0)
		self.assertEqual(sub.units_allocated, 0.0)

		sub.workflow_state = "Approved"
		sub.approved_by_operations = 1
		with self.assertRaises(frappe.ValidationError):
			sub.submit()

	def test_02_subscription_posting_exact_numbers_and_gl_lifecycle(self) -> None:
		"""Verify exact pricing calculations, 3-row GL posting, and cancellation lifecycle:

		Gross 10,000,000.00, Fee 1%, Offer 115.452000 ->
		- Fee = 100,000.00
		- Net = 9,900,000.00
		- Units = 85749.922045
		- GL: 3 rows balancing to 0
		- Cancel: GL net zero, unit balance unchanged
		"""
		make_approved_valuation(self.fund, date=nowdate(), nav=115.452000, bid=115.452000, offer=115.452000)

		initial_unit_balance = get_unit_balance(self.investor, self.fund)
		self.assertEqual(initial_unit_balance, Decimal("0.000000"))

		sub = frappe.new_doc("Asset Subscription")
		sub.investor = self.investor
		sub.fund = self.fund
		sub.subscription_date = nowdate()
		sub.gross_amount = 10000000.00
		sub.entry_fee_pct = 1.0
		sub.maker = "Administrator"
		sub.checker = self.checker
		# Test setup: ignore_permissions required
		sub.insert(ignore_permissions=True)

		self.assertEqual(flt(sub.applicable_nav_price, 6), 115.452000)
		self.assertEqual(flt(sub.entry_fee_amount, 2), 100000.00)
		self.assertEqual(flt(sub.net_invested_amount, 2), 9900000.00)
		self.assertEqual(flt(sub.units_allocated, 6), 85749.922045)
		self.assertEqual(sub.status, "Draft")

		sub.approved_by_operations = 1
		sub.workflow_state = "Approved"
		sub.submit()

		self.assertEqual(sub.status, "Submitted")
		bal_after_sub = get_unit_balance(self.investor, self.fund)
		self.assertEqual(bal_after_sub, Decimal("85749.922045"))

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

		cash_entry = next(e for e in gl_entries if e.account == self.fund_doc.client_cash_payable_account)
		self.assertEqual(Decimal(str(cash_entry.debit)), Decimal("10000000.00"))
		self.assertEqual(cash_entry.party_type, "Supplier")
		self.assertTrue(bool(cash_entry.party))

		capital_entry = next(e for e in gl_entries if e.account == self.fund_doc.unitholders_capital_account)
		self.assertEqual(Decimal(str(capital_entry.credit)), Decimal("9900000.00"))

		fee_entry = next(e for e in gl_entries if e.account == self.fund_doc.entry_fee_payable_account)
		self.assertEqual(Decimal(str(fee_entry.credit)), Decimal("100000.00"))

		sub.cancel()
		self.assertEqual(sub.status, "Cancelled")

		bal_after_cancel = get_unit_balance(self.investor, self.fund)
		self.assertEqual(bal_after_cancel, Decimal("0.000000"))

		all_gl_entries = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Asset Subscription", "voucher_no": sub.name},
			fields=["debit", "credit", "is_cancelled"],
		)
		net_gl = sum(Decimal(str(e.debit)) - Decimal(str(e.credit)) for e in all_gl_entries)
		self.assertEqual(net_gl, Decimal("0.00"))

	def test_03_agent_commission_gl_posting_in_fund_manager_company(self) -> None:
		"""Verify that agent commission generates liability GL entries in the Fund Manager
		company and that cancellation marks the commission row Cancelled and reverses GL.
		"""
		ag = make_agent(
			agent_code="AGT-R09-01",
			agent_name="R09 Test Brokerage Agent",
			commission_rate_pct=0.50,
		)
		make_approved_valuation(self.fund, date=nowdate(), nav=115.452000, bid=115.452000, offer=115.452000)

		sub = frappe.new_doc("Asset Subscription")
		sub.investor = self.investor
		sub.fund = self.fund
		sub.subscription_date = nowdate()
		sub.gross_amount = 10000000.00
		sub.entry_fee_pct = 1.0
		sub.agent = ag.name
		sub.agent_commission_pct = 0.50
		sub.maker = "Administrator"
		sub.checker = self.checker
		# Test setup: ignore_permissions required
		sub.insert(ignore_permissions=True)

		self.assertEqual(flt(sub.agent_commission_amount, 2), 50000.00)

		sub.approved_by_operations = 1
		sub.workflow_state = "Approved"
		sub.submit()

		settings = frappe.get_single("Fund Management Settings")
		fm_gl_entries = frappe.get_all(
			"GL Entry",
			filters={
				"voucher_type": "Asset Subscription",
				"voucher_no": sub.name,
				"company": self.fm_company,
			},
			fields=["account", "debit", "credit"],
		)
		self.assertEqual(len(fm_gl_entries), 2)
		exp_entry = next(e for e in fm_gl_entries if e.account == settings.commission_expense_account)
		self.assertEqual(Decimal(str(exp_entry.debit)), Decimal("50000.00"))
		pay_entry = next(e for e in fm_gl_entries if e.account == settings.commission_payable_account)
		self.assertEqual(Decimal(str(pay_entry.credit)), Decimal("50000.00"))

		comm = frappe.get_doc("Asset Agent Commission", {"subscription": sub.name})
		self.assertEqual(comm.payment_status, "Accrued")
		self.assertEqual(flt(comm.commission_amount, 2), 50000.00)

		sub.cancel()
		comm.reload()
		self.assertEqual(comm.payment_status, "Cancelled")

		all_gl_entries = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Asset Subscription", "voucher_no": sub.name},
			fields=["debit", "credit"],
		)
		net_gl = sum(Decimal(str(e.debit)) - Decimal(str(e.credit)) for e in all_gl_entries)
		self.assertEqual(net_gl, Decimal("0.00"))
