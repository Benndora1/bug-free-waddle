"""Integration tests for Asset Investment Limit Setup DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from asset_management.tests.factories import make_checker_user, make_fund, make_security

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetInvestmentLimitSetup(IntegrationTestCase):
	def test_asset_class_limit_breach_blocks_trade_order(self) -> None:
		dealer = make_checker_user("dealer.lim@example.com")
		approver = make_checker_user("approver.lim@example.com")
		fund = make_fund(fund_id="TEST-LIM-BAL", total_nav=10_000_000.0, total_gav=10_000_000.0)
		sec = make_security(
			security_code="TEST-LIM-EQ",
			instrument_type="Listed Equity",
			asset_class="Quoted Equity",
			current_market_price=100.0,
		)

		if not frappe.db.exists("Asset Investment Limit Setup", "LIM-DT-EQ-20"):
			lim = frappe.new_doc("Asset Investment Limit Setup")
			lim.fund = fund.name
			lim.rule_type = "Asset Class Limit"
			lim.target_asset_class = "Quoted Equity"
			lim.max_allocation_pct = 20.0
			lim.enforce_strict_block = 1
			# Test setup: ignore_permissions required
			lim.insert(ignore_permissions=True, set_name="LIM-DT-EQ-20")

		order = frappe.new_doc("Asset Trade Order Header")
		order.order_date = nowdate()
		order.settlement_date = nowdate()
		order.order_type = "BUY"
		order.fund = fund.name
		order.security = sec.name
		order.counterparty = "Secondary Exchange"
		order.face_value = 22000.0  # 2,200,000 = 22% of 10,000,000 NAV (> 20% limit, within 25% cash)
		order.clean_price_pct = 100.0
		order.dealer = dealer
		order.approver = approver
		order.approval_status = "Approved"
		# Test setup: ignore_permissions required
		order.insert(ignore_permissions=True)

		self.assertEqual(order.compliance_status, "Breached")
		with self.assertRaises(frappe.ValidationError):
			order.submit()
