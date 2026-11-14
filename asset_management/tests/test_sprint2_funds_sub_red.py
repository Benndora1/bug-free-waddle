import unittest

import frappe
from frappe.utils import add_days, flt, nowdate


class TestSprint2FundsSubRed(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")

		# Ensure clean state for test investors across multiple runs using primary key deletion
		for dt in [
			"Asset Investor Portfolio",
			"Asset Investor Register Line",
			"Asset Unit Ledger Entry",
			"Asset Subscription",
			"Asset Redemption",
			"Asset Fund Switch",
			"Asset Agent Commission",
		]:
			names = frappe.get_all(
				dt, filters={"investor": ["in", ["__TEST_INV_S2_01", "__TEST_INV_S2_02"]]}, pluck="name"
			)
			if names:
				frappe.db.delete(dt, {"name": ["in", names]})
		frappe.db.commit()

		# Create or ensure test checker user exists
		if not frappe.db.exists("User", "test_checker@example.com"):
			u = frappe.new_doc("User")
			u.email = "test_checker@example.com"
			u.first_name = "Test"
			u.last_name = "Checker"
			u.send_welcome_email = 0
			u.insert(ignore_permissions=True)

		# Create or ensure test investors exist
		if not frappe.db.exists("Asset Investor", "__TEST_INV_S2_01"):
			inv = frappe.new_doc("Asset Investor")
			inv.investor_id = "__TEST_INV_S2_01"
			inv.investor_name = "Grace Namubiru"
			inv.investor_type = "Individual"
			inv.identification_type = "National ID"
			inv.tax_id = "CM9011223344"
			inv.phone = "+256772111222"
			inv.bank_name = "Stanbic Bank Uganda"
			inv.bank_branch = "Main Branch"
			inv.bank_account_name = "Grace Namubiru"
			inv.bank_account_no = "9030012345678"
			inv.status = "Active"
			inv.kyc_status = "Verified"
			inv.insert(ignore_permissions=True)
		else:
			frappe.db.set_value("Asset Investor", "__TEST_INV_S2_01", "tax_id", "CM9011223344")

		if not frappe.db.exists("Asset Investor", "__TEST_INV_S2_02"):
			inv2 = frappe.new_doc("Asset Investor")
			inv2.investor_id = "__TEST_INV_S2_02"
			inv2.investor_name = "Victoria Capital Partners"
			inv2.investor_type = "Corporate"
			inv2.identification_type = "Certificate of Incorporation"
			inv2.tax_id = "CO-889900"
			inv2.phone = "+256414998877"
			inv2.bank_name = "Stanbic Bank Uganda"
			inv2.bank_branch = "Corporate Branch"
			inv2.bank_account_name = "Victoria Capital Partners"
			inv2.bank_account_no = "9030099887766"
			inv2.status = "Active"
			inv2.kyc_status = "Verified"
			inv2.insert(ignore_permissions=True)

		# Ensure Fund SBG-MMF is active and valuation approved
		mmf = frappe.get_doc("Asset Fund", "SBG-MMF")
		mmf.status = "Active"
		mmf.prior_day_valuation_approved = 1
		mmf.current_nav_per_unit = 100.0
		mmf.bid_offer_spread_pct = 0.0
		mmf.current_offer_price = 100.0
		mmf.current_bid_price = 100.0
		mmf.last_valuation_date = nowdate()
		mmf.save(ignore_permissions=True)

		# Ensure Fund SBG-BAL is active and valuation approved
		bal = frappe.get_doc("Asset Fund", "SBG-BAL")
		bal.status = "Active"
		bal.prior_day_valuation_approved = 1
		bal.current_nav_per_unit = 120.0
		bal.bid_offer_spread_pct = 1.0
		bal.last_valuation_date = nowdate()
		bal.save(ignore_permissions=True)

		frappe.db.commit()

	def test_01_fund_setup_and_spread_pricing(self):
		"""Verify standard fund parameters, fee structures, and bid-offer spread pricing."""
		mmf = frappe.get_doc("Asset Fund", "SBG-MMF")
		self.assertEqual(mmf.fund_type, "Money Market Fund")
		self.assertEqual(mmf.currency, "UGX")
		self.assertEqual(mmf.accounting_basis, "Amortised Cost")
		self.assertEqual(mmf.current_offer_price, mmf.current_bid_price)

		# Check fee schedule
		fee_types = [f.fee_type for f in mmf.fees]
		self.assertIn("Management Fee", fee_types)
		self.assertIn("Custody Fee", fee_types)
		self.assertIn("Trustee Fee", fee_types)

		# Balanced fund with 1% spread: NAV 120 -> Offer 121.20, Bid 118.80
		bal = frappe.get_doc("Asset Fund", "SBG-BAL")
		self.assertEqual(bal.bid_offer_spread_pct, 1.0)
		self.assertAlmostEqual(bal.current_offer_price, 120.0 * 1.01, places=2)
		self.assertAlmostEqual(bal.current_bid_price, 120.0 * 0.99, places=2)

	def test_02_subscription_creation_and_threshold_enforcement(self):
		"""Verify minimum threshold validation and successful unit creation on subscription."""
		# 1. Below threshold (25,000 < 100,000 min)
		sub_fail = frappe.new_doc("Asset Subscription")
		sub_fail.investor = "__TEST_INV_S2_01"
		sub_fail.fund = "SBG-MMF"
		sub_fail.gross_amount = 25000.0
		with self.assertRaises(frappe.ValidationError):
			sub_fail.insert(ignore_permissions=True)

		# 2. Valid initial subscription: 5,000,000 UGX at NAV 100.0 -> 50,000 units
		sub = frappe.new_doc("Asset Subscription")
		sub.investor = "__TEST_INV_S2_01"
		sub.fund = "SBG-MMF"
		sub.gross_amount = 5000000.0
		sub.payment_method = "Bank Transfer / BOL"
		sub.maker = "Administrator"
		sub.checker = "test_checker@example.com"
		sub.insert(ignore_permissions=True)
		frappe.db.commit()

		self.assertEqual(sub.units_allocated, 50000.0)
		self.assertEqual(sub.net_invested_amount, 5000000.0)

		# Maker == Checker should fail validation
		sub_mc = frappe.new_doc("Asset Subscription")
		sub_mc.investor = "__TEST_INV_S2_01"
		sub_mc.fund = "SBG-MMF"
		sub_mc.gross_amount = 5000000.0
		sub_mc.maker = "Administrator"
		sub_mc.checker = "Administrator"
		sub_mc.insert(ignore_permissions=True)
		sub_mc.workflow_state = "Approved"
		with self.assertRaises(frappe.ValidationError):
			sub_mc.submit()
		frappe.db.rollback()

		# Reload sub from DB, approve, and submit
		sub = frappe.get_doc("Asset Subscription", sub.name)
		sub.maker = "Administrator"
		sub.checker = "test_checker@example.com"
		sub.approved_by_operations = 1
		sub.workflow_state = "Approved"
		sub.submit()
		frappe.db.commit()

		self.assertEqual(sub.status, "Submitted")
		self.assertTrue(sub.contract_note_no.startswith("CN-"))

		# Verify Investor Portfolio
		port_id = "__TEST_INV_S2_01-SBG-MMF"
		self.assertTrue(frappe.db.exists("Asset Investor Portfolio", port_id))
		port = frappe.get_doc("Asset Investor Portfolio", port_id)
		self.assertEqual(port.total_units, 50000.0)
		self.assertEqual(port.total_invested_amount, 5000000.0)
		self.assertEqual(port.current_market_value, 5000000.0)

		# Verify Register Entry
		reg_lines = frappe.get_all("Asset Investor Register Line", filters={"voucher_no": sub.name})
		self.assertEqual(len(reg_lines), 1)
		reg = frappe.get_doc("Asset Investor Register Line", reg_lines[0].name)
		self.assertEqual(reg.entry_type, "Subscription")
		self.assertEqual(reg.units, 50000.0)
		self.assertEqual(reg.running_unit_balance, 50000.0)

	def test_03_subscription_additional_threshold(self):
		"""Verify additional subscription limit (50,000 min) for existing unit holder."""
		# 1. Below additional limit (30,000 < 50,000)
		sub_fail = frappe.new_doc("Asset Subscription")
		sub_fail.investor = "__TEST_INV_S2_01"
		sub_fail.fund = "SBG-MMF"
		sub_fail.gross_amount = 30000.0
		with self.assertRaises(frappe.ValidationError):
			sub_fail.insert(ignore_permissions=True)

		# 2. Valid additional subscription: 1,000,000 UGX
		sub = frappe.new_doc("Asset Subscription")
		sub.investor = "__TEST_INV_S2_01"
		sub.fund = "SBG-MMF"
		sub.gross_amount = 1000000.0
		sub.maker = "Administrator"
		sub.checker = "test_checker@example.com"
		sub.insert(ignore_permissions=True)
		sub.approved_by_operations = 1
		sub.workflow_state = "Approved"
		sub.submit()

		port = frappe.get_doc("Asset Investor Portfolio", "__TEST_INV_S2_01-SBG-MMF")
		self.assertEqual(port.total_units, 60000.0)
		self.assertEqual(port.total_invested_amount, 6000000.0)

	def test_04_agent_referral_and_commission_accrual(self):
		"""Verify agent referral and automatic agent commission ledger entry."""
		sub = frappe.new_doc("Asset Subscription")
		sub.investor = "__TEST_INV_S2_02"
		sub.fund = "SBG-MMF"
		sub.gross_amount = 10000000.0
		sub.agent = "AGT-001"  # 0.50% commission
		sub.maker = "Administrator"
		sub.checker = "test_checker@example.com"
		sub.insert(ignore_permissions=True)
		sub.approved_by_operations = 1
		sub.workflow_state = "Approved"

		self.assertEqual(sub.agent_commission_pct, 0.50)
		self.assertEqual(sub.agent_commission_amount, 50000.0)
		sub.submit()

		# Check Asset Agent Commission was generated
		comms = frappe.get_all("Asset Agent Commission", filters={"subscription": sub.name})
		self.assertEqual(len(comms), 1)
		comm = frappe.get_doc("Asset Agent Commission", comms[0].name)
		self.assertEqual(comm.agent, "AGT-001")
		self.assertEqual(comm.commission_amount, 50000.0)
		self.assertEqual(comm.payment_status, "Accrued")

	def test_05_rule_1_prior_day_valuation_guard_on_redemptions(self):
		"""Verify strict Operational Rule 1: No redemption without approved prior-day valuation."""
		red = frappe.new_doc("Asset Redemption")
		red.investor = "__TEST_INV_S2_01"
		red.fund = "SBG-MMF"
		red.redemption_by = "Units"
		red.requested_units = 5000.0
		red.prior_day_valuation_approved = 0  # Unchecked!

		with self.assertRaises(frappe.ValidationError):
			red.insert(ignore_permissions=True)

	def test_06_redemption_unit_and_balance_validations(self):
		"""Verify unit overdraft guard and minimum retained balance guard."""
		# 1. Overdraft: Investor has 60,000 units; requests 70,000 units
		red_od = frappe.new_doc("Asset Redemption")
		red_od.investor = "__TEST_INV_S2_01"
		red_od.fund = "SBG-MMF"
		red_od.prior_day_valuation_approved = 1
		red_od.redemption_by = "Units"
		red_od.requested_units = 70000.0
		with self.assertRaises(frappe.ValidationError):
			red_od.insert(ignore_permissions=True)

		# 2. Min balance breach: Investor has 60,000 units (6M UGX). If redeems 59,500 units,
		# remaining is 500 units = 50,000 UGX, which is below min_balance_amount of 100,000 UGX!
		red_bal = frappe.new_doc("Asset Redemption")
		red_bal.investor = "__TEST_INV_S2_01"
		red_bal.fund = "SBG-MMF"
		red_bal.prior_day_valuation_approved = 1
		red_bal.redemption_by = "Units"
		red_bal.requested_units = 59500.0
		with self.assertRaises(frappe.ValidationError):
			red_bal.insert(ignore_permissions=True)

	def test_07_redemption_execution_and_tax_deduction(self):
		"""Verify successful redemption with 15% WHT deduction, portfolio update, and payout staging."""
		port = frappe.get_doc("Asset Investor Portfolio", "__TEST_INV_S2_01-SBG-MMF")
		self.assertEqual(port.total_units, 60000.0)

		frappe.db.set_value(
			"Asset Fund",
			"SBG-MMF",
			{"wht_basis": "Gross Proceeds", "wht_rate": 15.0},
		)
		try:
			# Redeem 10,000 units at NAV 100.0 -> Gross = 1,000,000 UGX
			# WHT (15%) = 150,000 UGX -> Net Payout = 850,000 UGX
			red = frappe.new_doc("Asset Redemption")
			red.investor = "__TEST_INV_S2_01"
			red.fund = "SBG-MMF"
			red.prior_day_valuation_approved = 1
			red.redemption_by = "Units"
			red.requested_units = 10000.0
			red.maker = "Administrator"
			red.checker = "test_checker@example.com"
			red.insert(ignore_permissions=True)

			self.assertEqual(red.gross_redemption_amount, 1000000.0)
			self.assertEqual(red.withholding_tax_amount, 150000.0)
			self.assertEqual(red.net_payout_amount, 850000.0)
			self.assertEqual(red.remaining_units, 50000.0)

			# Checker sign-off & submit
			red.checker_approved = 1
			red.workflow_state = "Approved"
			red.submit()

			self.assertEqual(red.status, "Submitted")
			self.assertEqual(red.payment_status, "Pending Payment")

			# Verify portfolio reduction
			port.reload()
			self.assertEqual(port.total_units, 50000.0)
			self.assertEqual(port.total_withdrawn_amount, 850000.0)

			# Verify Unit Ledger Entry (No Register Line)
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
		finally:
			frappe.db.set_value(
				"Asset Fund",
				"SBG-MMF",
				{"wht_basis": "None", "wht_rate": 0.0},
			)

	def test_08_inter_fund_switch_bid_offer_settlement(self):
		"""Verify inter-fund switch: source units redeemed at Bid Price, target units allocated at Offer Price."""
		from decimal import ROUND_DOWN, Decimal

		# Grace switches 10,000 units from SBG-MMF (Bid 100.0) to SBG-BAL (Offer 121.20)
		# Gross out = 10,000 * 100 = 1,000,000 UGX
		# Target units = 1,000,000 / 121.20 = 8250.825082 units (6 dp ROUND_DOWN)
		swi = frappe.new_doc("Asset Fund Switch")
		swi.investor = "__TEST_INV_S2_01"
		swi.from_fund = "SBG-MMF"
		swi.to_fund = "SBG-BAL"
		swi.switch_by = "Units"
		swi.switch_units = 10000.0
		swi.maker = "Administrator"
		swi.checker = "test_checker@example.com"
		swi.insert(ignore_permissions=True)

		self.assertEqual(swi.gross_switch_amount, 1000000.0)
		self.assertEqual(swi.net_switch_amount, 1000000.0)
		bal_fund = frappe.get_doc("Asset Fund", "SBG-BAL")
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

		# Source portfolio should drop from 50,000 to 40,000 units
		mmf_port = frappe.get_doc("Asset Investor Portfolio", "__TEST_INV_S2_01-SBG-MMF")
		self.assertEqual(mmf_port.total_units, 40000.0)

		# Target portfolio should exist with allocated units
		bal_port = frappe.get_doc("Asset Investor Portfolio", "__TEST_INV_S2_01-SBG-BAL")
		self.assertAlmostEqual(bal_port.total_units, expected_target_units, places=6)

		# No Register Line; Two Unit Ledger Entries (Switch Out and Switch In)
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

	def test_09_bol_statement_import_and_client_auto_matching(self):
		"""Verify BOL statement CSV import, client matching, and automated subscription creation."""
		csv_data = """Value Date,Transaction Description,Amount,Fund Code
2026-10-31,FT to SBGS from CM9011223344 Grace Namubiru MMF,2500000,SBG-MMF
2026-10-31,EFT Stanbic 9030099887766 Victoria Capital,15000000,SBG-MMF
2026-10-31,Deposit by Unregistered Client Unknown,500000,SBG-MMF
"""
		bol = frappe.new_doc("Asset BOL Import Header")
		bol.file_name = "BOL_STMT_STANBIC_20261031.csv"
		bol.bank_name = "Stanbic Bank Uganda"
		bol.bank_account_no = "9030005544332"
		bol.insert(ignore_permissions=True)

		bol.parse_bol_statement(csv_data)
		self.assertEqual(bol.total_lines, 3)
		self.assertEqual(bol.matched_lines, 2)
		self.assertEqual(bol.exception_lines, 1)

		# Check Line 1 matched Grace Namubiru via ID
		l1 = bol.lines[0]
		self.assertEqual(l1.status, "Matched")
		self.assertEqual(l1.matched_investor, "__TEST_INV_S2_01")
		self.assertEqual(l1.match_method, "Investor ID Match")

		# Check Line 2 matched Victoria Capital via Bank Account
		l2 = bol.lines[1]
		self.assertEqual(l2.status, "Matched")
		self.assertEqual(l2.matched_investor, "__TEST_INV_S2_02")
		self.assertEqual(l2.match_method, "Bank Account Match")

		# Check Line 3 is Exception
		l3 = bol.lines[2]
		self.assertEqual(l3.status, "Exception")
		self.assertTrue("No matching investor" in l3.exception_reason)

		# Convert matched lines to Subscriptions
		res = bol.create_subscriptions()
		self.assertEqual(res["created_subscriptions"], 2)

		bol.reload()
		self.assertEqual(bol.lines[0].status, "Subscription Created")
		self.assertTrue(bool(bol.lines[0].subscription_ref))
		self.assertTrue(frappe.db.exists("Asset Subscription", bol.lines[0].subscription_ref))

	def test_10_bol_48_hour_unallocated_exception_escalation(self):
		"""Verify Operational Procedures 4.10: 48-hour unallocated deposits escalate to supervisor and AML log."""
		bol = frappe.new_doc("Asset BOL Import Header")
		bol.file_name = "BOL_STMT_UNALLOCATED.csv"
		bol.insert(ignore_permissions=True)

		# Add an unallocated exception line dated 3 days ago (> 48 hours)
		three_days_ago = add_days(nowdate(), -3)
		bol.append(
			"lines",
			{
				"line_no": 1,
				"value_date": three_days_ago,
				"transaction_description": "Unknown deposit ref 998877 without client info",
				"amount": 25000000.0,
				"fund_code": "SBG-MMF",
				"status": "Exception",
				"exception_reason": "No client match found",
				"unallocated_since": three_days_ago,
			},
		)
		bol.save(ignore_permissions=True)

		# Run SLA check
		res = bol.check_unallocated_sla(threshold_hours=48.0)
		self.assertGreaterEqual(res["escalated_count"], 1)

		bol.reload()
		line = bol.lines[0]
		self.assertEqual(line.escalated_to_supervisor, 1)
		self.assertGreaterEqual(line.unallocated_hours, 48.0)

		# Verify Suspicious Transaction Log was created
		ref = f"{bol.name}-{line.line_no}"
		self.assertTrue(frappe.db.exists("Asset Suspicious Transaction Log", {"transaction_reference": ref}))
		log = frappe.get_doc("Asset Suspicious Transaction Log", {"transaction_reference": ref})
		self.assertEqual(log.rule, "AML_UNALLOCATED")
		self.assertEqual(log.status, "Investigating")
		self.assertEqual(log.action_taken, "None")


if __name__ == "__main__":
	unittest.main()
