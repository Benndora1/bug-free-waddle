"""Integration tests for Asset Investor Application DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, nowdate

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetInvestorApplication(IntegrationTestCase):
	def test_application_risk_scoring_and_investor_creation(self) -> None:
		ident_no = "__TEST_DT_APP_01"
		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.investor_type = "Individual"
		app.client_category = "Retail"
		app.investor_name = "Application Test Client"
		app.identification_type = "National ID"
		app.identification_no = ident_no
		app.tax_id = "TIN-APP-01"
		app.email = "app.client@example.com"
		app.phone = "+15551112222"
		app.physical_address = "10 Park Avenue"
		app.bank_name = "First Commercial Bank"
		app.bank_branch = "Main"
		app.bank_account_name = "Application Test Client"
		app.bank_account_no = "90100112233"
		# Test setup: ignore_permissions required
		app.insert(ignore_permissions=True)

		app.load_required_documents()
		for k in frappe.get_all("Asset Investor KYC Document", filters={"parent_application": app.name}):
			frappe.db.set_value(
				"Asset Investor KYC Document",
				k.name,
				{
					"attachment": "/files/kyc.pdf",
					"verification_status": "Verified",
					"expiry_date": add_to_date(nowdate(), years=3),
				},
			)

		chk = app.run_verification_checks()
		self.assertEqual(chk["risk_tier"], "Low")
		app.reload()
		app.submit()
		self.assertTrue(frappe.db.exists("Asset Investor", ident_no))
