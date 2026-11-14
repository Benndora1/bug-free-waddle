"""Integration tests for funds, subscriptions, redemptions, switches, and BOL imports (Sprint 2)."""

from decimal import ROUND_DOWN, Decimal

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from asset_management.tests.factories import (
	make_agent,
	make_checker_user,
	make_fund,
	make_investor,
	make_subscription,
)


class TestSprint2FundsSubRed(IntegrationTestCase):
	def setUp(self) -> None:
		super().setUp()
		frappe.set_user("Administrator")
		self.checker = make_checker_user("test_checker@example.com")

		self.mmf = make_fund(
			fund_id="TEST-S2-MMF",
			fund_name="Test Money Market Scheme",
			fund_type="Money Market Fund",
			nav=100.0,
			bid=100.0,
			offer=100.0,
			accounting_basis="Amortised Cost",
			bid_offer_spread_pct=0.0,
			min_subscription_amount=100000.0,
			min_additional_amount=50000.0,
			min_redemption_amount=50000.0,
			min_balance_amount=100000.0,
		)
		self.bal = make_fund(
			fund_id="TEST-S2-BAL",
			fund_name="Test Balanced Scheme",
			fund_type="Balanced Fund",
			nav=120.0,
			bid=118.8,
			offer=121.2,
			bid_offer_spread_pct=1.0,
			min_subscription_amount=100000.0,
			min_additional_amount=50000.0,
			min_redemption_amount=50000.0,
			min_balance_amount=100000.0,
		)

		self.inv1 = make_investor(
			investor_name="Grace Rivera",
			investor_type="Individual",
		)
		self.inv2 = make_investor(
			investor_name="Horizon Capital Partners",
			investor_type="Corporate",
		)
		self.agent = make_agent(
			agent_code="AGT-S2-001",
			agent_name="Standard Agency Intermediary",
			commission_rate_pct=0.50,
		)

	def test_01_fund_setup_and_spread_pricing(self) -> None:
		"""Verify standard fund parameters, fee structures, and bid-offer spread pricing."""
		mmf = frappe.get_doc("Asset Fund", self.mmf.name)
		self.assertEqual(mmf.fund_type, "Money Market Fund")
		self.assertEqual(mmf.currency, "USD")
		self.assertEqual(mmf.accounting_basis, "Amortised Cost")
		self.assertEqual(mmf.current_offer_price, mmf.current_bid_price)

		fee_types = [f.fee_type for f in mmf.fees]
		self.assertIn("Management Fee", fee_types)
		self.assertIn("Custody Fee", fee_types)
		self.assertIn("Trustee Fee", fee_types)

		bal = frappe.get_doc("Asset Fund", self.bal.name)
		self.assertEqual(bal.bid_offer_spread_pct, 1.0)
		self.assertAlmostEqual(bal.current_offer_price, 120.0 * 1.01, places=2)
		self.assertAlmostEqual(bal.current_bid_price, 120.0 * 0.99, places=2)

	def test_02_subscription_creation_and_threshold_enforcement(self) -> None:
		"""Verify minimum threshold validation, maker-checker, and unit creation on subscription."""
		sub_fail = frappe.new_doc("Asset Subscription")
		sub_fail.investor = self.inv1.name
		sub_fail.fund = self.mmf.name
		sub_fail.gross_amount = 25000.0
		with self.assertRaises(frappe.ValidationError):
			sub_fail.insert(ignore_permissions=True)

		# Maker == Checker should fail validation
		sub_mc = frappe.new_doc("Asset Subscription")
		sub_mc.investor = self.inv1.name
		sub_mc.fund = self.mmf.name
		sub_mc.gross_amount = 5000000.0
		sub_mc.maker = "Administrator"
		sub_mc.checker = "Administrator"
		# Test setup: ignore_permissions required
		sub_mc.insert(ignore_permissions=True)
		sub_mc.workflow_state = "Approved"
		with self.assertRaises(frappe.ValidationError):
			sub_mc.submit()

		sub = frappe.new_doc("Asset Subscription")
		sub.investor = self.inv1.name
		sub.fund = self.mmf.name
		sub.gross_amount = 5000000.0
		sub.payment_method = "Bank Transfer / BOL"
		sub.maker = "Administrator"
		sub.checker = self.checker
		# Test setup: ignore_permissions required
		sub.insert(ignore_permissions=True)

		self.assertEqual(sub.units_allocated, 50000.0)
		self.assertEqual(sub.net_invested_amount, 5000000.0)

		sub.approved_by_operations = 1
		sub.workflow_state = "Approved"
		sub.submit()

		self.assertEqual(sub.status, "Submitted")
		self.assertTrue(sub.contract_note_no.startswith("CN-"))

		port_id = f"{self.inv1.name}-{self.mmf.name}"
		self.assertTrue(frappe.db.exists("Asset Investor Portfolio", port_id))
		port = frappe.get_doc("Asset Investor Portfolio", port_id)
		self.assertEqual(port.total_units, 50000.0)
		self.assertEqual(port.total_invested_amount, 5000000.0)
		self.assertEqual(port.current_market_value, 5000000.0)

		reg_lines = frappe.get_all("Asset Investor Register Line", filters={"voucher_no": sub.name})
		self.assertEqual(len(reg_lines), 1)
		reg = frappe.get_doc("Asset Investor Register Line", reg_lines[0].name)
		self.assertEqual(reg.entry_type, "Subscription")
		self.assertEqual(reg.units, 50000.0)
		self.assertEqual(reg.running_unit_balance, 50000.0)

	def test_03_subscription_additional_threshold(self) -> None:
		"""Verify additional subscription limit (50,000 min) for existing unit holder."""
		make_subscription(self.inv1.name, self.mmf.name, amount=5000000.0, checker_user=self.checker)

		sub_fail = frappe.new_doc("Asset Subscription")
		sub_fail.investor = self.inv1.name
		sub_fail.fund = self.mmf.name
		sub_fail.gross_amount = 30000.0
		with self.assertRaises(frappe.ValidationError):
			sub_fail.insert(ignore_permissions=True)

		make_subscription(self.inv1.name, self.mmf.name, amount=1000000.0, checker_user=self.checker)

		port = frappe.get_doc("Asset Investor Portfolio", f"{self.inv1.name}-{self.mmf.name}")
		self.assertEqual(port.total_units, 60000.0)
		self.assertEqual(port.total_invested_amount, 6000000.0)

	def test_04_agent_referral_and_commission_accrual(self) -> None:
		"""Verify agent referral and automatic agent commission ledger entry."""
		sub = frappe.new_doc("Asset Subscription")
		sub.investor = self.inv2.name
		sub.fund = self.mmf.name
		sub.gross_amount = 10000000.0
		sub.agent = self.agent.name
		sub.maker = "Administrator"
		sub.checker = self.checker
		# Test setup: ignore_permissions required
		sub.insert(ignore_permissions=True)
		sub.approved_by_operations = 1
		sub.workflow_state = "Approved"

		self.assertEqual(sub.agent_commission_pct, 0.50)
		self.assertEqual(sub.agent_commission_amount, 50000.0)
		sub.submit()

		comms = frappe.get_all("Asset Agent Commission", filters={"subscription": sub.name})
		self.assertEqual(len(comms), 1)
		comm = frappe.get_doc("Asset Agent Commission", comms[0].name)
		self.assertEqual(comm.agent, self.agent.name)
		self.assertEqual(comm.commission_amount, 50000.0)
		self.assertEqual(comm.payment_status, "Accrued")

	def test_05_rule_1_prior_day_valuation_guard_on_redemptions(self) -> None:
		"""Verify strict Operational Rule 1: No redemption without approved prior-day valuation."""
		make_subscription(self.inv1.name, self.mmf.name, amount=1000000.0, checker_user=self.checker)
		red = frappe.new_doc("Asset Redemption")
		red.investor = self.inv1.name
		red.fund = self.mmf.name
		red.redemption_by = "Units"
		red.requested_units = 5000.0
		red.prior_day_valuation_approved = 0

		with self.assertRaises(frappe.ValidationError):
			red.insert(ignore_permissions=True)

	def test_06_redemption_unit_and_balance_validations(self) -> None:
		"""Verify unit overdraft guard and minimum retained balance guard."""
		make_subscription(self.inv1.name, self.mmf.name, amount=6000000.0, checker_user=self.checker)

		red_od = frappe.new_doc("Asset Redemption")
		red_od.investor = self.inv1.name
		red_od.fund = self.mmf.name
		red_od.prior_day_valuation_approved = 1
		red_od.redemption_by = "Units"
		red_od.requested_units = 70000.0
		with self.assertRaises(frappe.ValidationError):
			red_od.insert(ignore_permissions=True)

		red_bal = frappe.new_doc("Asset Redemption")
		red_bal.investor = self.inv1.name
		red_bal.fund = self.mmf.name
		red_bal.prior_day_valuation_approved = 1
		red_bal.redemption_by = "Units"
		red_bal.requested_units = 59500.0
		with self.assertRaises(frappe.ValidationError):
			red_bal.insert(ignore_permissions=True)

	def test_07_redemption_execution_and_tax_deduction(self) -> None:
		"""Verify successful redemption with 15% WHT deduction, portfolio update, and payout staging."""
		make_subscription(self.inv1.name, self.mmf.name, amount=6000000.0, checker_user=self.checker)
		port = frappe.get_doc("Asset Investor Portfolio", f"{self.inv1.name}-{self.mmf.name}")
		self.assertEqual(port.total_units, 60000.0)

		frappe.db.set_value(
			"Asset Fund",
			self.mmf.name,
			{"wht_basis": "Gross Proceeds", "wht_rate": 15.0},
		)
		red = frappe.new_doc("Asset Redemption")
		red.investor = self.inv1.name
		red.fund = self.mmf.name
		red.prior_day_valuation_approved = 1
		red.redemption_by = "Units"
		red.requested_units = 10000.0
		red.maker = "Administrator"
		red.checker = self.checker
		# Test setup: ignore_permissions required
		red.insert(ignore_permissions=True)

		self.assertEqual(red.gross_redemption_amount, 1000000.0)
		self.assertEqual(red.withholding_tax_amount, 150000.0)
		self.assertEqual(red.net_payout_amount, 850000.0)
		self.assertEqual(red.remaining_units, 50000.0)

		red.checker_approved = 1
		red.workflow_state = "Approved"
		red.submit()

		self.assertEqual(red.status, "Submitted")
		self.assertEqual(red.payment_status, "Pending Payment")

		port.reload()
		self.assertEqual(port.total_units, 50000.0)
		self.assertEqual(port.total_withdrawn_amount, 850000.0)

		reg_lines = frappe.get_all("Asset Investor Register Line", filters={"voucher_no": red.name})
		self.assertEqual(len(reg_lines), 0)
		ule_rows = frappe.get_all(
			"Asset Unit Ledger Entry",
			filters={"voucher_no": red.name, "is_cancelled": 0},
			fields=["entry_type", "units", "amount"],
		)
		self.assertEqual(len(ule_rows), 1)
		self.assertEqual(ule_rows[0].entry_type, "Redemption")
		self.assertEqual(ule_rows[0].units, -10000.0)

	def test_08_inter_fund_switch_bid_offer_settlement(self) -> None:
		"""Verify inter-fund switch: source units redeemed at Bid Price, target units allocated at Offer Price."""
		make_subscription(self.inv1.name, self.mmf.name, amount=5000000.0, checker_user=self.checker)

		swi = frappe.new_doc("Asset Fund Switch")
		swi.investor = self.inv1.name
		swi.from_fund = self.mmf.name
		swi.to_fund = self.bal.name
		swi.switch_by = "Units"
		swi.switch_units = 10000.0
		swi.maker = "Administrator"
		swi.checker = self.checker
		# Test setup: ignore_permissions required
		swi.insert(ignore_permissions=True)

		self.assertEqual(swi.gross_switch_amount, 1000000.0)
		self.assertEqual(swi.net_switch_amount, 1000000.0)
		bal_fund = frappe.get_doc("Asset Fund", self.bal.name)
		expected_target_units = float(
			(Decimal("1000000.00") / Decimal(str(bal_fund.current_offer_price))).quantize(
				Decimal("0.000001"), rounding=ROUND_DOWN
			)
		)
		self.assertAlmostEqual(swi.units_allocated_to_fund, expected_target_units, places=6)

		swi.approved_by_checker = 1
		swi.workflow_state = "Approved"
		swi.submit()

		self.assertEqual(swi.status, "Submitted")

		mmf_port = frappe.get_doc("Asset Investor Portfolio", f"{self.inv1.name}-{self.mmf.name}")
		self.assertEqual(mmf_port.total_units, 40000.0)

		bal_port = frappe.get_doc("Asset Investor Portfolio", f"{self.inv1.name}-{self.bal.name}")
		self.assertAlmostEqual(bal_port.total_units, expected_target_units, places=6)

		regs = frappe.get_all("Asset Investor Register Line", filters={"voucher_no": swi.name})
		self.assertEqual(len(regs), 0)
		ule_rows = frappe.get_all(
			"Asset Unit Ledger Entry",
			filters={"voucher_no": swi.name, "is_cancelled": 0},
			fields=["entry_type", "units"],
		)
		self.assertEqual(len(ule_rows), 2)
		types = [r.entry_type for r in ule_rows]
		self.assertIn("Switch Out", types)
		self.assertIn("Switch In", types)

	def test_09_bol_statement_import_and_client_auto_matching(self) -> None:
		"""Verify BOL statement CSV import, client matching, and automated subscription creation."""
		bol_inv1 = make_investor(
			investor_id="INV-BOL-S2-01",
			investor_name="Grace Rivera",
			investor_type="Individual",
			tax_id="ID9011223344",
			bank_account_no="9030012345678",
		)
		bol_inv2 = make_investor(
			investor_id="INV-BOL-S2-02",
			investor_name="Horizon Capital Partners",
			investor_type="Corporate",
			tax_id="CO-889900",
			bank_account_no="9030099887766",
		)
		csv_data = f"""Value Date,Transaction Description,Amount,Fund Code
2026-10-31,FT from {bol_inv1.investor_id} Grace Rivera MMF,2500000,{self.mmf.name}
2026-10-31,EFT {bol_inv2.bank_account_no} Horizon Capital,15000000,{self.mmf.name}
2026-10-31,Deposit by Unregistered Client Unknown,500000,{self.mmf.name}
"""
		bol = frappe.new_doc("Asset BOL Import Header")
		bol.file_name = "BOL_STMT_20261031.csv"
		bol.bank_name = "First Commercial Bank"
		bol.bank_account_no = "9030005544332"
		# Test setup: ignore_permissions required
		bol.insert(ignore_permissions=True)

		bol.parse_bol_statement(csv_data)
		self.assertEqual(bol.total_lines, 3)
		self.assertEqual(bol.matched_lines, 2)
		self.assertEqual(bol.exception_lines, 1)

		l1 = bol.lines[0]
		self.assertEqual(l1.status, "Matched")
		self.assertEqual(l1.matched_investor, bol_inv1.name)
		self.assertEqual(l1.match_method, "Investor ID Match")

		l2 = bol.lines[1]
		self.assertEqual(l2.status, "Matched")
		self.assertEqual(l2.matched_investor, bol_inv2.name)
		self.assertEqual(l2.match_method, "Bank Account Match")

		l3 = bol.lines[2]
		self.assertEqual(l3.status, "Exception")
		self.assertIn("No matching investor", l3.exception_reason)

		res = bol.create_subscriptions()
		self.assertEqual(res["created_subscriptions"], 2)

		bol.reload()
		self.assertEqual(bol.lines[0].status, "Subscription Created")
		self.assertTrue(bool(bol.lines[0].subscription_ref))
		self.assertTrue(frappe.db.exists("Asset Subscription", bol.lines[0].subscription_ref))

	def test_10_bol_48_hour_unallocated_exception_escalation(self) -> None:
		"""Verify 48-hour unallocated deposits escalate to supervisor and AML log."""
		bol = frappe.new_doc("Asset BOL Import Header")
		bol.file_name = "BOL_STMT_UNALLOCATED.csv"
		# Test setup: ignore_permissions required
		bol.insert(ignore_permissions=True)

		three_days_ago = add_days(nowdate(), -3)
		bol.append(
			"lines",
			{
				"line_no": 1,
				"value_date": three_days_ago,
				"transaction_description": "Unknown deposit ref 998877 without client info",
				"amount": 25000000.0,
				"fund_code": self.mmf.name,
				"status": "Exception",
				"exception_reason": "No client match found",
				"unallocated_since": three_days_ago,
			},
		)
		# Test setup: ignore_permissions required
		bol.save(ignore_permissions=True)

		res = bol.check_unallocated_sla(threshold_hours=48.0)
		self.assertGreaterEqual(res["escalated_count"], 1)

		bol.reload()
		line = bol.lines[0]
		self.assertEqual(line.escalated_to_supervisor, 1)
		self.assertGreaterEqual(line.unallocated_hours, 48.0)

		ref = f"{bol.name}-{line.line_no}"
		self.assertTrue(frappe.db.exists("Asset Suspicious Transaction Log", {"transaction_reference": ref}))
		log = frappe.get_doc("Asset Suspicious Transaction Log", {"transaction_reference": ref})
		self.assertEqual(log.rule, "AML_UNALLOCATED")
		self.assertEqual(log.status, "Investigating")
		self.assertEqual(log.action_taken, "None")
