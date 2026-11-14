"""Integration tests for Asset Risk Profile DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetRiskProfile(IntegrationTestCase):
	def test_risk_profile_tiers_classify_applicant_score(self) -> None:
		self.assertTrue(frappe.db.exists("Asset Risk Profile", "LOW_RISK"))
		self.assertTrue(frappe.db.exists("Asset Risk Profile", "HIGH_RISK"))

		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.investor_type = "Individual"
		app.client_category = "Retail"
		app.investor_name = "Low Risk Applicant"
		app.identification_type = "National ID"
		app.identification_no = "__TEST_RISK_DT_01"
		app.tax_id = "TIN-RISK-01"
		app.email = "risk.dt@example.com"
		app.phone = "+15557778888"
		app.physical_address = "200 Elm St"
		app.bank_name = "First Commercial Bank"
		app.bank_branch = "Main"
		app.bank_account_name = "Low Risk Applicant"
		app.bank_account_no = "90100778899"
		app.pep_status = "No"
		# Test setup: ignore_permissions required
		app.insert(ignore_permissions=True)

		chk = app.run_verification_checks()
		self.assertEqual(chk["risk_tier"], "Low")
