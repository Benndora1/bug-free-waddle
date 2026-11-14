"""Integration tests for Asset Custody Instruction DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from asset_management.tests.factories import make_checker_user, make_fund, make_security

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetCustodyInstruction(IntegrationTestCase):
	def test_dual_signature_requirement_and_settlement(self) -> None:
		dealer = make_checker_user("dealer.cust@example.com")
		approver = make_checker_user("approver.cust@example.com")
		fund = make_fund(fund_id="TEST-CUST-BND", total_aum=10_000_000_000.0)
		sec = make_security(security_code="TEST-CUST-SEC-01")

		order = frappe.new_doc("Asset Trade Order Header")
		order.order_date = nowdate()
		order.settlement_date = nowdate()
		order.order_type = "BUY"
		order.fund = fund.name
		order.security = sec.name
		order.counterparty = "Global Markets"
		order.face_value = 1000000.0
		order.clean_price_pct = 99.0
		order.dealer = dealer
		order.approver = approver
		order.approval_status = "Approved"
		# Test setup: ignore_permissions required
		order.insert(ignore_permissions=True)
		order.submit()

		cust = frappe.get_doc("Asset Custody Instruction", order.custody_instruction_ref)
		cust.maker_signed = 1
		cust.checker_signed = 0
		with self.assertRaises(frappe.ValidationError):
			cust.submit()

		cust.reload()
		cust.maker_signed = 1
		cust.checker_signed = 1
		cust.submit()
		self.assertEqual(cust.status, "Authorized & Dispatched")
