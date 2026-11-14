"""Integration tests for Asset PEP Sanction Setup DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetPEPSanctionSetup(IntegrationTestCase):
	def test_pep_rule_triggers_edd_on_investor_application(self) -> None:
		self.assertTrue(frappe.db.exists("Asset PEP Sanction Setup", "PEP_MATCH"))

		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.investor_type = "Individual"
		app.client_category = "High Net Worth"
		app.investor_name = "PEP Test Applicant"
		app.identification_type = "Passport"
		app.identification_no = "__TEST_PEP_DT_01"
		app.tax_id = "TIN-PEP-01"
		app.email = "pep.dt@example.com"
		app.phone = "+15553334444"
		app.physical_address = "1 Capitol Square"
		app.bank_name = "First Commercial Bank"
		app.bank_branch = "Main"
		app.bank_account_name = "PEP Test Applicant"
		app.bank_account_no = "90100334455"
		app.pep_status = "Yes"
		# Test setup: ignore_permissions required
		app.insert(ignore_permissions=True)

		chk = app.run_verification_checks()
		self.assertEqual(chk["edd_required"], 1)
		self.assertEqual(chk["risk_tier"], "High")
