"""Integration tests for print formats and script reports (Sprint 5)."""

import importlib

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from asset_management.tests.factories import (
	make_checker_user,
	make_fund,
	make_investor,
	make_security,
	make_security_price,
	make_subscription,
)


class TestSprint5PostingAndReports(IntegrationTestCase):
	def setUp(self) -> None:
		super().setUp()
		frappe.set_user("Administrator")
		self.checker = make_checker_user("test_checker@example.com")
		self.dealer = make_checker_user("test_dealer@example.com")

		self.fund_doc = make_fund(
			fund_id="TEST-S5-MMF",
			fund_name="Test S5 Money Market Fund",
			fund_type="Money Market Fund",
			nav=100.0,
			bid=100.0,
			offer=100.0,
			custodian_name="Global Custody Bank Ltd",
			custodian_address="100 Financial Plaza, Suite 400",
			custodian_account="CUST-S5-001",
		)
		self.fund = self.fund_doc.name

		self.inv_doc = make_investor(
			investor_id="__TEST_INV_S5_01",
			investor_name="S5 Institutional Investor",
			investor_type="Corporate",
		)
		self.investor = self.inv_doc.name

		# Create a submitted subscription (creates portfolio & unit ledger)
		existing_sub = frappe.db.get_value(
			"Asset Subscription", {"investor": self.investor, "fund": self.fund, "docstatus": 1}, "name"
		)
		if existing_sub:
			self.sub = frappe.get_doc("Asset Subscription", existing_sub)
		else:
			self.sub = make_subscription(
				investor=self.investor,
				fund=self.fund,
				amount=1_000_000.0,
				subscription_date=nowdate(),
				checker_user=self.checker,
			)

		# Create security, price, holding, trade order, custody instruction, and approved valuation
		self.sec = make_security(
			security_code="TEST-S5-BOND-2030",
			security_name="12.500% Treasury Bond 2030",
			instrument_type="Treasury Bond",
			asset_class="Treasury Bond",
			coupon_rate=12.500,
			coupon_rate_pct=12.500,
			maturity_date=add_days(nowdate(), 365),
			current_market_price=98.500,
		)
		make_security_price(
			security=self.sec.name,
			price_date=nowdate(),
			clean_price=98.500,
			source="Manual",
		)

		existing_ord = frappe.db.get_value(
			"Asset Trade Order Header",
			{"fund": self.fund, "security": self.sec.name, "docstatus": 1},
			"name",
		)
		if existing_ord:
			ord_doc = frappe.get_doc("Asset Trade Order Header", existing_ord)
		else:
			ord_doc = frappe.new_doc("Asset Trade Order Header")
			ord_doc.order_date = nowdate()
			ord_doc.settlement_date = nowdate()
			ord_doc.order_type = "BUY"
			ord_doc.fund = self.fund
			ord_doc.security = self.sec.name
			ord_doc.counterparty = "Global Markets Counterparty"
			ord_doc.face_value = 500000.0
			ord_doc.clean_price_pct = 98.500
			ord_doc.dealer = self.dealer
			ord_doc.approver = self.checker
			ord_doc.approval_status = "Approved"
			# Test setup: ignore_permissions required
			ord_doc.insert(ignore_permissions=True)
			ord_doc.submit()

		self.custody_instruction = frappe.get_doc(
			"Asset Custody Instruction", ord_doc.custody_instruction_ref
		)

		existing_val = frappe.db.get_value(
			"Asset Fund Valuation", {"fund": self.fund, "docstatus": 1}, "name"
		)
		if existing_val:
			self.valuation = frappe.get_doc("Asset Fund Valuation", existing_val)
		else:
			val = frappe.new_doc("Asset Fund Valuation")
			val.fund = self.fund
			val.valuation_date = nowdate()
			val.cash_bank_balance = 505000.0
			val.prepared_by = "Administrator"
			val.approved_by = self.checker
			# Test setup: ignore_permissions required
			val.insert(ignore_permissions=True)
			val.submit()
			self.valuation = val

	def test_01_print_format_unit_trust_contract_note(self) -> None:
		"""Verify Unit Trust Contract Note print format rendering and layout fields."""
		pf = frappe.get_doc("Print Format", "Unit Trust Contract Note")
		rendered = frappe.render_template(pf.html, {"doc": self.sub, "frappe": frappe})

		self.assertIn("Institutional Asset Management", rendered)
		self.assertIn("Unit Trust Subscription Contract Note", rendered)
		self.assertIn(self.sub.investor_name, rendered)
		self.assertIn(self.sub.fund_name, rendered)
		self.assertIn(f"{self.sub.units_allocated:,.4f}", rendered)

	def test_02_print_format_statement_of_investment(self) -> None:
		"""Verify Statement of Investment portfolio valuation statement rendering."""
		port = frappe.get_doc("Asset Investor Portfolio", f"{self.investor}-{self.fund}")
		pf = frappe.get_doc("Print Format", "Statement of Investment")
		rendered = frappe.render_template(pf.html, {"doc": port, "frappe": frappe})

		self.assertIn("INSTITUTIONAL ASSET MANAGEMENT", rendered)
		self.assertIn("Statement of Portfolio Valuation", rendered)
		self.assertIn(port.investor_name, rendered)
		self.assertIn(port.fund_name, rendered)
		self.assertIn(f"{port.total_units:,.4f}", rendered)

	def test_03_print_format_custody_instruction(self) -> None:
		"""Verify Custody Instruction print format renders dynamic fund custodian details."""
		pf = frappe.get_doc("Print Format", "Custody Instruction")
		rendered = frappe.render_template(pf.html, {"doc": self.custody_instruction, "frappe": frappe})

		self.assertIn("Attention: Head, Investor Services", rendered)
		self.assertIn("Global Custody Bank Ltd", rendered)
		self.assertIn("100 Financial Plaza, Suite 400", rendered)
		self.assertIn("CUST-S5-001", rendered)
		self.assertIn(self.custody_instruction.counterparty, rendered)
		self.assertIn(f"{self.custody_instruction.face_value:,.0f}", rendered)

	def test_04_report_unit_holders_register_execution(self) -> None:
		"""Verify Unit Holders Register script report returns seeded investor holding row."""
		mod = importlib.import_module(
			"asset_management.asset_management.report.unit_holders_register.unit_holders_register"
		)
		cols, data = mod.execute(filters={"fund": self.fund})

		col_fields = [c["fieldname"] for c in cols]
		self.assertIn("fund", col_fields)
		self.assertIn("investor", col_fields)
		self.assertIn("total_units", col_fields)
		self.assertIn("current_market_value", col_fields)

		self.assertGreaterEqual(len(data), 1)
		matching = [r for r in data if r["investor"] == self.investor]
		self.assertEqual(len(matching), 1)
		self.assertEqual(matching[0]["fund"], self.fund)
		self.assertEqual(matching[0]["total_units"], 10000.0)

	def test_05_report_unit_holders_register_filters(self) -> None:
		"""Verify filtering unit holders register by specific investor account."""
		mod = importlib.import_module(
			"asset_management.asset_management.report.unit_holders_register.unit_holders_register"
		)
		_cols, data = mod.execute(filters={"investor": self.investor})

		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["investor"], self.investor)
		self.assertEqual(data[0]["total_units"], 10000.0)

	def test_06_report_daily_fund_valuation_summary_execution(self) -> None:
		"""Verify Daily Fund Valuation Summary script report returns seeded valuation and reconciles math."""
		mod = importlib.import_module(
			"asset_management.asset_management.report.daily_fund_valuation_summary.daily_fund_valuation_summary"
		)
		cols, data = mod.execute(filters={"fund": self.fund})

		col_fields = [c["fieldname"] for c in cols]
		self.assertIn("total_gav", col_fields)
		self.assertIn("total_accrued_expenses", col_fields)
		self.assertIn("total_nav", col_fields)
		self.assertIn("nav_per_unit", col_fields)

		self.assertGreaterEqual(len(data), 1)
		for row in data:
			self.assertAlmostEqual(
				row["total_nav"], row["total_gav"] - row["total_accrued_expenses"], places=2
			)

	def test_07_report_portfolio_performance_and_asset_allocation(self) -> None:
		"""Verify Portfolio Performance and Asset Allocation script report returns seeded holding."""
		mod = importlib.import_module(
			"asset_management.asset_management.report.portfolio_performance_and_asset_allocation.portfolio_performance_and_asset_allocation"
		)
		cols, data = mod.execute(filters={"fund": self.fund})

		col_fields = [c["fieldname"] for c in cols]
		self.assertIn("security", col_fields)
		self.assertIn("asset_class", col_fields)
		self.assertIn("face_value", col_fields)
		self.assertIn("dirty_market_value", col_fields)

		self.assertGreaterEqual(len(data), 1)
		sec_rows = [r for r in data if r.get("security") == self.sec.name]
		self.assertEqual(len(sec_rows), 1)
		self.assertEqual(sec_rows[0]["face_value"], 500000.0)

	def test_08_report_maturity_profile_and_cash_flow_projection(self) -> None:
		"""Verify Maturity Profile and Cash Flow Projection script report returns seeded bond."""
		mod = importlib.import_module(
			"asset_management.asset_management.report.maturity_profile_and_cash_flow_projection.maturity_profile_and_cash_flow_projection"
		)
		cols, data = mod.execute(filters={"asset_class": "Treasury Bond"})

		col_fields = [c["fieldname"] for c in cols]
		self.assertIn("security_id", col_fields)
		self.assertIn("days_to_maturity", col_fields)
		self.assertIn("coupon_rate", col_fields)

		self.assertGreaterEqual(len(data), 1)
		for row in data:
			self.assertEqual(row["asset_class"], "Treasury Bond")
			self.assertGreaterEqual(row["days_to_maturity"], 0)
