"""Integration tests for Asset Investor KYC Document DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from asset_management.tests.factories import make_investor

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetInvestorKYCDocument(IntegrationTestCase):
	def test_kyc_document_expiry_flags_investor_kyc_status(self) -> None:
		inv = make_investor()
		doc = frappe.new_doc("Asset Investor KYC Document")
		doc.investor = inv.name
		doc.document_code = "NAT_ID"
		doc.document_name = "National ID"
		doc.is_mandatory = 1
		doc.attachment = "/files/id.pdf"
		doc.verification_status = "Verified"
		doc.expiry_date = add_days(nowdate(), -5)
		# Test setup: ignore_permissions required
		doc.insert(ignore_permissions=True)

		summary = inv.get_kyc_status_summary()
		self.assertTrue(summary["has_expired"])
		doc.reload()
		self.assertEqual(doc.verification_status, "Expired")
		inv.reload()
		self.assertEqual(inv.kyc_status, "Pending")
