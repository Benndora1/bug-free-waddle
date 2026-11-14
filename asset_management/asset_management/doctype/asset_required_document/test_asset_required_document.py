"""Integration tests for Asset Required Document DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetRequiredDocument(IntegrationTestCase):
	def test_required_documents_loaded_into_application_by_investor_type(self) -> None:
		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.investor_type = "Corporate"
		app.client_category = "Institutional"
		app.investor_name = "Required Doc Test Corp"
		app.identification_type = "Certificate of Incorporation"
		app.identification_no = "__TEST_REQ_DOC_CORP"
		app.tax_id = "TIN-REQ-01"
		app.email = "req.corp@example.com"
		app.phone = "+15556667777"
		app.physical_address = "100 Corporate Blvd"
		app.bank_name = "First Commercial Bank"
		app.bank_branch = "Main"
		app.bank_account_name = "Required Doc Test Corp"
		app.bank_account_no = "90100667788"
		# Test setup: ignore_permissions required
		app.insert(ignore_permissions=True)

		res = app.load_required_documents()
		self.assertGreater(res["total_required"], 0)
		codes = frappe.get_all(
			"Asset Investor KYC Document",
			filters={"parent_application": app.name},
			pluck="document_code",
		)
		self.assertIn("CERT_INCORP", codes)
