"""Integration tests for Asset Trade Order Header DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate

from asset_management.tests.factories import make_checker_user, make_fund, make_security

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetTradeOrderHeader(IntegrationTestCase):
	def test_trade_order_consideration_and_holding_creation(self) -> None:
		dealer = make_checker_user("dealer.toh@example.com")
		approver = make_checker_user("approver.toh@example.com")
		fund = make_fund(fund_id="TEST-TOH-BND", total_aum=10_000_000_000.0)
		sec = make_security(security_code="TEST-TOH-SEC-01", coupon_rate=10.0, coupon_rate_pct=10.0)

		order = frappe.new_doc("Asset Trade Order Header")
		order.order_date = nowdate()
		order.settlement_date = nowdate()
		order.order_type = "BUY"
		order.fund = fund.name
		order.security = sec.name
		order.counterparty = "Primary Dealer"
		order.face_value = 2000000.0
		order.clean_price_pct = 98.0
		order.dealer = dealer
		order.approver = approver
		order.approval_status = "Approved"
		# Test setup: ignore_permissions required
		order.insert(ignore_permissions=True)

		self.assertEqual(flt(order.consideration_amount, 2), 1960000.0)
		order.submit()
		self.assertTrue(frappe.db.exists("Asset Portfolio Holding", f"{fund.name}-{sec.name}"))
