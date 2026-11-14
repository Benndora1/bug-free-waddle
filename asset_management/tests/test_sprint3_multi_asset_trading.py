"""Integration tests for multi-asset trading, pre-trade compliance, and custody instructions (Sprint 3)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from asset_management.tests.factories import make_checker_user, make_fund, make_security


class TestSprint3MultiAssetTrading(IntegrationTestCase):
	def setUp(self) -> None:
		super().setUp()
		frappe.set_user("Administrator")
		self.dealer = make_checker_user("test_dealer@example.com")
		self.approver = make_checker_user("test_im@example.com")

		self.mmf = make_fund(
			fund_id="TEST-S3-MMF",
			fund_name="Test S3 Money Market Fund",
			fund_type="Money Market Fund",
			nav=100.0,
			total_aum=50_000_000_000.0,
			custodian_name="Primary Custodian Bank",
		)
		self.bnd = make_fund(
			fund_id="TEST-S3-BND",
			fund_name="Test S3 Bond Fund",
			fund_type="Fixed Income / Bond Fund",
			nav=100.0,
			total_aum=20_000_000_000.0,
			custodian_name="Primary Custodian Bank",
		)
		self.bal = make_fund(
			fund_id="TEST-S3-BAL",
			fund_name="Test S3 Balanced Fund",
			fund_type="Balanced Fund",
			nav=100.0,
			total_aum=10_000_000_000.0,
			custodian_name="Primary Custodian Bank",
		)

		self.bond_1 = make_security(
			security_code="TEST-BOND-2039",
			security_name="15.800% 23-Jun-2039 Treasury Bond",
			instrument_type="Treasury Bond",
			asset_class="Treasury Bond",
			issuer="Sovereign Treasury",
			issue_date="2024-06-23",
			maturity_date="2039-06-23",
			coupon_rate=15.800,
			coupon_rate_pct=15.800,
			coupon_frequency="Semi-Annual",
			day_count_convention="Actual/365",
			current_market_price=93.547,
		)
		self.bond_2 = make_security(
			security_code="TEST-BOND-2035",
			security_name="16.000% 08-Nov-2035 Treasury Bond",
			instrument_type="Treasury Bond",
			asset_class="Treasury Bond",
			issuer="Sovereign Treasury",
			issue_date="2023-11-08",
			maturity_date="2035-11-08",
			coupon_rate=16.000,
			coupon_rate_pct=16.000,
			coupon_frequency="Semi-Annual",
			day_count_convention="Actual/365",
			current_market_price=99.657,
		)
		self.tbill = make_security(
			security_code="TBILL-364D-2027",
			security_name="364-Day Treasury Bill",
			instrument_type="Treasury Bill",
			asset_class="Treasury Bill",
			issuer="Sovereign Treasury",
			issue_date="2026-01-01",
			maturity_date="2026-12-31",
			coupon_rate=0.0,
			coupon_rate_pct=0.0,
			coupon_frequency="Zero Coupon / Discount",
			day_count_convention="Actual/364",
			current_market_price=88.100,
		)
		self.fd = make_security(
			security_code="FD-BANK-180D",
			security_name="180-Day Bank Fixed Deposit",
			instrument_type="Fixed Deposit",
			asset_class="Fixed Deposit",
			issuer="First Commercial Bank",
			issue_date="2026-01-01",
			maturity_date="2026-06-30",
			coupon_rate=12.0,
			coupon_rate_pct=12.0,
			coupon_frequency="At Maturity",
			day_count_convention="Actual/365",
			current_market_price=100.0,
		)
		self.equity = make_security(
			security_code="EQ-LISTED-A",
			security_name="Listed Telecom Corp",
			instrument_type="Listed Equity",
			asset_class="Quoted Equity",
			issuer="Listed Telecom Corp",
			issue_date="2020-01-01",
			coupon_rate=0.0,
			coupon_rate_pct=0.0,
			current_market_price=240.0,
		)

		# Create 30% Quoted Equity limit on TEST-S3-BAL
		if not frappe.db.exists("Asset Investment Limit Setup", "LIM-S3-BAL-EQ"):
			lim = frappe.new_doc("Asset Investment Limit Setup")
			lim.fund = self.bal.name
			lim.rule_type = "Asset Class Limit"
			lim.target_asset_class = "Quoted Equity"
			lim.min_allocation_pct = 0.0
			lim.max_allocation_pct = 30.0
			lim.enforce_strict_block = 1
			# Test setup: ignore_permissions required
			lim.insert(ignore_permissions=True, set_name="LIM-S3-BAL-EQ")

	def test_01_security_master_and_auto_coupon_schedule(self) -> None:
		"""Verify bond security master and automated semi-annual coupon schedule generation."""
		sec = frappe.get_doc("Asset Investment Security", self.bond_1.name)
		self.assertEqual(sec.asset_class, "Treasury Bond")
		self.assertEqual(sec.coupon_rate, 15.800)
		self.assertEqual(sec.coupon_frequency, "Semi-Annual")
		self.assertEqual(sec.day_count_convention, "Actual/365")

		self.assertGreater(len(sec.coupon_schedule), 10)
		c1 = sec.coupon_schedule[0]
		self.assertEqual(c1.coupon_number, 1)
		self.assertEqual(c1.coupon_rate, 7.90)

	def test_02_treasury_bond_purchase_clean_dirty_price_calculation(self) -> None:
		"""Verify T-Bond purchase clean and dirty price consideration and accrued interest."""
		order = frappe.new_doc("Asset Trade Order Header")
		order.order_date = "2025-07-25"
		order.settlement_date = "2025-07-25"
		order.order_type = "BUY"
		order.fund = self.bnd.name
		order.security = self.bond_1.name
		order.counterparty = "Primary Global Markets"
		order.face_value = 180800000.0
		order.clean_price_pct = 93.547
		order.yield_to_maturity = 17.150
		order.days_accrued = 32
		order.dealer = self.dealer
		order.approver = self.approver
		order.approval_status = "Approved"
		# Test setup: ignore_permissions required
		order.insert(ignore_permissions=True)

		expected_consideration = round(180800000.0 * 0.93547, 2)
		self.assertEqual(order.consideration_amount, 169132976.0)
		self.assertAlmostEqual(order.consideration_amount, expected_consideration, places=2)

		expected_accrued = round(180800000.0 * 0.158 * 32 / 365.0, 2)
		self.assertAlmostEqual(order.accrued_interest, expected_accrued, places=2)

		expected_settlement = round(order.consideration_amount + order.accrued_interest, 2)
		self.assertEqual(order.settlement_amount, expected_settlement)
		self.assertGreater(order.dirty_price, order.clean_price_pct)

	def test_03_treasury_bill_discount_basis(self) -> None:
		"""Verify Treasury Bill trade on discount basis."""
		order = frappe.new_doc("Asset Trade Order Header")
		order.order_date = nowdate()
		order.settlement_date = nowdate()
		order.order_type = "BUY"
		order.fund = self.mmf.name
		order.security = self.tbill.name
		order.counterparty = "Central Bank Primary Auction"
		order.face_value = 500000000.0
		order.clean_price_pct = 88.100
		order.yield_to_maturity = 13.50
		order.dealer = self.dealer
		order.approver = self.approver
		order.approval_status = "Approved"
		# Test setup: ignore_permissions required
		order.insert(ignore_permissions=True)

		expected_settlement = round(500000000.0 * 0.881, 2)
		self.assertEqual(order.consideration_amount, expected_settlement)
		self.assertEqual(order.settlement_amount, 440500000.0)
		self.assertEqual(order.accrued_interest, 0.0)

	def test_04_fixed_deposit_placement_accrual_projection(self) -> None:
		"""Verify Fixed Deposit placement and interest maturity calculation."""
		order = frappe.new_doc("Asset Trade Order Header")
		order.order_date = nowdate()
		order.settlement_date = nowdate()
		order.order_type = "PLACEMENT"
		order.fund = self.mmf.name
		order.security = self.fd.name
		order.counterparty = "First Commercial Bank Treasury"
		order.face_value = 1000000000.0
		order.deposit_tenor_days = 180
		order.interest_rate = 12.0
		order.dealer = self.dealer
		order.approver = self.approver
		order.approval_status = "Approved"
		# Test setup: ignore_permissions required
		order.insert(ignore_permissions=True)

		self.assertEqual(order.consideration_amount, 1000000000.0)
		self.assertEqual(order.settlement_amount, 1000000000.0)
		expected_interest = round(1000000000.0 * 0.12 * 180 / 365.0, 2)
		self.assertAlmostEqual(order.expected_interest, expected_interest, places=2)
		self.assertEqual(order.maturity_date, add_days(order.order_date, 180))

	def test_05_quoted_equity_trade_calculation(self) -> None:
		"""Verify Quoted Equity trade consideration and brokerage fee settlement."""
		order = frappe.new_doc("Asset Trade Order Header")
		order.order_date = nowdate()
		order.settlement_date = add_days(nowdate(), 3)
		order.order_type = "BUY"
		order.fund = self.bal.name
		order.security = self.equity.name
		order.counterparty = "Secondary Exchange Market"
		order.face_value = 500000.0
		order.clean_price_pct = 240.0
		order.brokerage_commission = 1200000.0
		order.dealer = self.dealer
		order.approver = self.approver
		order.approval_status = "Approved"
		# Test setup: ignore_permissions required
		order.insert(ignore_permissions=True)

		self.assertEqual(order.consideration_amount, 120000000.0)
		self.assertEqual(order.settlement_amount, 121200000.0)

	def test_06_pre_trade_compliance_cash_overdraft_block(self) -> None:
		"""Verify Foundational Rule 2: Trade exceeding available cash triggers compliance breach."""
		order = frappe.new_doc("Asset Trade Order Header")
		order.order_date = nowdate()
		order.settlement_date = nowdate()
		order.order_type = "BUY"
		order.fund = self.mmf.name
		order.security = self.bond_1.name
		order.counterparty = "Primary Global Markets"
		order.face_value = 100000000000.0
		order.clean_price_pct = 95.0
		order.dealer = self.dealer
		order.approver = self.approver
		order.approval_status = "Approved"
		# Test setup: ignore_permissions required
		order.insert(ignore_permissions=True)

		self.assertEqual(order.compliance_status, "Breached")
		self.assertIn("Cash Overdraft Breach", order.compliance_notes)

		with self.assertRaises(frappe.ValidationError):
			order.submit()

	def test_07_pre_trade_compliance_asset_class_limit_check(self) -> None:
		"""Verify pre-trade compliance checks fund asset allocation limit (30% equity limit)."""
		order = frappe.new_doc("Asset Trade Order Header")
		order.order_date = nowdate()
		order.settlement_date = nowdate()
		order.order_type = "BUY"
		order.fund = self.bal.name
		order.security = self.equity.name
		order.counterparty = "Secondary Exchange Market"
		order.face_value = 20000000.0
		order.clean_price_pct = 240.0
		order.dealer = self.dealer
		order.approver = self.approver
		order.approval_status = "Approved"
		# Test setup: ignore_permissions required
		order.insert(ignore_permissions=True)

		self.assertEqual(order.compliance_status, "Breached")
		self.assertIn("Asset Class Limit Breach", order.compliance_notes)

		with self.assertRaises(frappe.ValidationError):
			order.submit()

	def test_08_compliance_override_and_maker_checker_authorization(self) -> None:
		"""Verify override justification workflow, maker != checker governance, and portfolio holding creation."""
		order = frappe.new_doc("Asset Trade Order Header")
		order.order_date = nowdate()
		order.settlement_date = nowdate()
		order.order_type = "BUY"
		order.fund = self.bal.name
		order.security = self.equity.name
		order.counterparty = "Secondary Exchange Market"
		order.face_value = 20000000.0
		order.clean_price_pct = 240.0
		order.dealer = self.dealer
		order.approver = self.dealer
		order.approval_status = "Approved"
		order.override_approved = 1
		order.override_justification = "IC resolution #44 approved equity overweight."
		# Test setup: ignore_permissions required
		order.insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			order.submit()

		order.reload()
		order.approver = self.approver
		order.submit()

		self.assertEqual(order.status, "Approved")
		self.assertTrue(bool(order.custody_instruction_ref))

		holding_id = f"{self.bal.name}-{self.equity.name}"
		self.assertTrue(frappe.db.exists("Asset Portfolio Holding", holding_id))
		holding = frappe.get_doc("Asset Portfolio Holding", holding_id)
		self.assertEqual(holding.asset_class, "Quoted Equity")
		self.assertEqual(holding.face_value, 20000000.0)
		self.assertEqual(holding.carrying_cost, 4800000000.0)
		self.assertEqual(holding.holding_status, "Active")

	def test_09_custody_instruction_generation_and_dual_signature_settlement(self) -> None:
		"""Verify automated custody ticket creation and dual-signature settlement dispatch."""
		order = frappe.new_doc("Asset Trade Order Header")
		order.order_date = nowdate()
		order.settlement_date = nowdate()
		order.order_type = "BUY"
		order.fund = self.bnd.name
		order.security = self.bond_2.name
		order.counterparty = "Primary Global Markets"
		order.face_value = 500000000.0
		order.clean_price_pct = 99.657
		order.yield_to_maturity = 16.900
		order.dealer = self.dealer
		order.approver = self.approver
		order.approval_status = "Approved"
		# Test setup: ignore_permissions required
		order.insert(ignore_permissions=True)
		order.submit()

		cust_id = order.custody_instruction_ref
		self.assertTrue(bool(cust_id))
		self.assertTrue(frappe.db.exists("Asset Custody Instruction", cust_id))

		cust = frappe.get_doc("Asset Custody Instruction", cust_id)
		self.assertEqual(cust.transaction_type, "T-BOND PURCHASE")
		self.assertEqual(cust.face_value, 500000000.0)
		self.assertEqual(cust.clean_price, 99.657)
		self.assertEqual(cust.custodian_bank, "Primary Custodian Bank")

		cust.maker_signed = 1
		cust.checker_signed = 0
		with self.assertRaises(frappe.ValidationError):
			cust.submit()

		cust.reload()
		cust.maker_signed = 1
		cust.checker_signed = 1
		cust.submit()

		self.assertEqual(cust.status, "Authorized & Dispatched")
		order.reload()
		self.assertEqual(order.status, "Settled")
