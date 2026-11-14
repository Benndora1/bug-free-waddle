import os
import unittest

import frappe
from frappe.utils import add_days, add_to_date, now_datetime, nowdate


class TestSprint1OnboardingCRM(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.cleanup_test_data()

	@classmethod
	def tearDownClass(cls):
		cls.cleanup_test_data()

	@classmethod
	def cleanup_test_data(cls):
		"""Clean up test investor applications, investors, and interactions."""
		frappe.set_user("Administrator")
		for app in frappe.get_all(
			"Asset Investor Application", filters={"identification_no": ["like", "__TEST_%"]}
		):
			doc = frappe.get_doc("Asset Investor Application", app.name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("Asset Investor Application", app.name, force=True, ignore_permissions=True)

		for inv in frappe.get_all("Asset Investor", filters={"investor_id": ["like", "__TEST_%"]}):
			frappe.delete_doc("Asset Investor", inv.name, force=True, ignore_permissions=True)

		for ci in frappe.get_all("Asset Client Interaction", filters={"subject": ["like", "__TEST_%"]}):
			frappe.delete_doc("Asset Client Interaction", ci.name, force=True, ignore_permissions=True)

		frappe.db.commit()

	def test_01_asset_management_roles_exist(self):
		"""Verify all 9 Asset Management departmental roles exist."""
		expected_roles = [
			"Asset Management Operations",
			"Asset Investment Manager",
			"Asset Fund Administrator",
			"Asset Finance Officer",
			"Asset Compliance Officer",
			"Asset Client Service",
			"Asset Agent",
			"Asset Investor Portal User",
			"Asset Management Admin",
		]
		for r in expected_roles:
			self.assertTrue(frappe.db.exists("Role", r), f"Missing role: {r}")

	def test_02_required_documents_and_risk_profile_setup(self):
		"""Verify master setups for KYC Required Documents, Risk Profiles, and SLAs."""
		self.assertTrue(frappe.db.exists("Asset Required Document", "NAT_ID"))
		self.assertTrue(frappe.db.exists("Asset Required Document", "PROOF_ADDR"))
		self.assertTrue(frappe.db.exists("Asset Required Document", "CERT_INCORP"))

		self.assertTrue(frappe.db.exists("Asset Risk Profile", "LOW_RISK"))
		self.assertTrue(frappe.db.exists("Asset Risk Profile", "HIGH_RISK"))

		self.assertTrue(frappe.db.exists("Asset CRM SLA Setup", "SLA_STATEMENT"))
		self.assertTrue(frappe.db.exists("Asset CRM SLA Setup", "SLA_COMPLAINT"))

	def test_03_standard_retail_individual_onboarding_lifecycle(self):
		"""Test full onboarding lifecycle for a standard low-risk retail investor."""
		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.onboarding_channel = "Face to Face"
		app.investor_type = "Individual"
		app.client_category = "Retail"
		app.investor_name = "Jane Mukasa"
		app.identification_type = "National ID"
		app.identification_no = "__TEST_CM88012345XYZ"
		app.tax_id = "1002345678"
		app.country_of_residence = "Uganda"
		app.email = "jane.mukasa@example.com"
		app.phone = "+256772123456"
		app.physical_address = "Plot 12, Kampala Road, Kampala"
		app.bank_name = "Stanbic Bank Uganda"
		app.bank_branch = "Crested Towers"
		app.bank_account_name = "Jane Mukasa"
		app.bank_account_no = "9030012345678"
		app.settlement_currency = "UGX"
		app.pep_status = "No"
		app.sanction_status = "No"
		app.insert(ignore_permissions=True)

		self.assertEqual(app.status, "Draft")

		# 1. Load Required Documents
		res_docs = app.load_required_documents()
		self.assertGreater(res_docs["total_required"], 0)

		# Attach dummy file for mandatory docs
		req_kyc = frappe.get_all(
			"Asset Investor KYC Document",
			filters={"parent_application": app.name},
			fields=["name", "document_code"],
		)
		for k in req_kyc:
			frappe.db.set_value(
				"Asset Investor KYC Document",
				k.name,
				{
					"attachment": "/files/test_id.pdf",
					"verification_status": "Verified",
					"expiry_date": add_to_date(nowdate(), years=5),
				},
			)

		# 2. Run Verification & Risk Scoring
		chk = app.run_verification_checks()
		self.assertLessEqual(chk["risk_score"], 30.0)
		self.assertEqual(chk["risk_tier"], "Low")
		self.assertEqual(chk["edd_required"], 0)

		# 3. Submit & Approve Application
		app.reload()
		app.submit()

		self.assertEqual(app.status, "Approved")
		self.assertEqual(app.created_investor_account, "__TEST_CM88012345XYZ")

		# Verify Asset Investor Master record created
		self.assertTrue(frappe.db.exists("Asset Investor", "__TEST_CM88012345XYZ"))
		investor = frappe.get_doc("Asset Investor", "__TEST_CM88012345XYZ")
		self.assertEqual(investor.investor_name, "Jane Mukasa")
		self.assertEqual(investor.status, "Active")
		self.assertEqual(investor.risk_tier, "Low")
		self.assertEqual(investor.bank_account_no, "9030012345678")

	def test_04_high_risk_and_pep_application_requires_ce_approval(self):
		"""Verify strict regulatory rule: High-risk/PEP applicants require CE sign-off before approval."""
		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.onboarding_channel = "Wholesale / Direct"
		app.investor_type = "Individual"
		app.client_category = "High Net Worth"
		app.investor_name = "Hon. Peter Ssempa"
		app.identification_type = "Passport"
		app.identification_no = "__TEST_P88990011"
		app.tax_id = "1009988776"
		app.country_of_residence = "Uganda"
		app.email = "peter.ssempa@example.com"
		app.phone = "+256701998877"
		app.physical_address = "Nakasero Hill Road, Kampala"
		app.bank_name = "Stanbic Bank Uganda"
		app.bank_branch = "Crested Towers"
		app.bank_account_name = "Peter Ssempa"
		app.bank_account_no = "9030088990011"
		app.pep_status = "Yes"  # PEP Investor!
		app.sanction_status = "No"
		app.insert(ignore_permissions=True)

		app.load_required_documents()
		for k in frappe.get_all("Asset Investor KYC Document", filters={"parent_application": app.name}):
			frappe.db.set_value(
				"Asset Investor KYC Document",
				k.name,
				{"attachment": "/files/passport.pdf", "verification_status": "Verified"},
			)

		chk = app.run_verification_checks()
		self.assertGreater(chk["risk_score"], 60.0)
		self.assertEqual(chk["risk_tier"], "High")
		self.assertEqual(chk["edd_required"], 1)

		# Attempt to submit without CE approval -> Must throw validation error!
		app.reload()
		app.approved_by_ce = 0
		with self.assertRaises(frappe.ValidationError):
			app.submit()

		# Grant CE approval per Operational Procedures Manual 4.1.18 & submit
		app = frappe.get_doc("Asset Investor Application", app.name)
		app.approved_by_ce = 1
		app.edd_notes = "EDD conducted. Sources of funds verified from agricultural estates. CE approved."
		app.submit()

		self.assertEqual(app.status, "Approved")
		self.assertTrue(frappe.db.exists("Asset Investor", "__TEST_P88990011"))
		investor = frappe.get_doc("Asset Investor", "__TEST_P88990011")
		self.assertEqual(investor.pep_status, "Yes")
		self.assertEqual(investor.risk_tier, "High")

	def test_05_mandatory_kyc_missing_attachment_guard(self):
		"""Verify that an application cannot be approved if mandatory KYC document has no attachment."""
		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.investor_type = "Individual"
		app.client_category = "Retail"
		app.investor_name = "Missing Doc Client"
		app.identification_type = "National ID"
		app.identification_no = "__TEST_MISSING_KYC_01"
		app.tax_id = "1001112223"
		app.email = "missing.doc@example.com"
		app.phone = "+256782000111"
		app.physical_address = "Ntinda, Kampala"
		app.bank_name = "Stanbic Bank Uganda"
		app.bank_branch = "Crested Towers"
		app.bank_account_name = "Missing Doc"
		app.bank_account_no = "9030011122233"
		app.insert(ignore_permissions=True)

		app.load_required_documents()
		# Deliberately leave attachments blank
		app.reload()
		with self.assertRaises(frappe.ValidationError):
			app.submit()

	def test_06_corporate_application_with_signatories_and_beneficiaries(self):
		"""Test Corporate onboarding with multiple directors and Next of Kin beneficiaries."""
		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.investor_type = "Corporate"
		app.client_category = "Institutional"
		app.investor_name = "Victoria Agri Holdings Ltd"
		app.identification_type = "Certificate of Incorporation"
		app.identification_no = "__TEST_CORP_800123"
		app.tax_id = "5000123456"
		app.country_of_residence = "Uganda"
		app.email = "info@victoriaagri.co.ug"
		app.phone = "+256414123456"
		app.physical_address = "7th Street Industrial Area, Kampala"
		app.bank_name = "Stanbic Bank Uganda"
		app.bank_branch = "Corporate Branch"
		app.bank_account_name = "Victoria Agri Holdings Ltd"
		app.bank_account_no = "9030099881122"

		# Add Signatories
		app.append(
			"signatories",
			{
				"full_name": "Dr. Sarah Namutebi",
				"signatory_type": "Director",
				"identification_type": "National ID",
				"identification_no": "CM70011122",
				"phone": "+256772999000",
				"pep_status": "No",
			},
		)
		app.append(
			"signatories",
			{
				"full_name": "James Okello",
				"signatory_type": "Authorized Signatory",
				"identification_type": "National ID",
				"identification_no": "CM75022233",
				"phone": "+256701888111",
				"pep_status": "No",
			},
		)

		# Add Beneficiaries
		app.append(
			"beneficiaries",
			{
				"full_name": "Victoria Employee Trust Scheme",
				"relationship": "Trustee",
				"allocation_percent": 100.0,
				"phone": "+256414123456",
			},
		)

		app.insert(ignore_permissions=True)
		app.load_required_documents()

		for k in frappe.get_all("Asset Investor KYC Document", filters={"parent_application": app.name}):
			frappe.db.set_value(
				"Asset Investor KYC Document",
				k.name,
				{"attachment": "/files/corp_doc.pdf", "verification_status": "Verified"},
			)

		app.reload()
		app.submit()

		self.assertEqual(app.status, "Approved")
		self.assertTrue(frappe.db.exists("Asset Investor", "__TEST_CORP_800123"))

	def test_07_crm_client_interaction_lifecycle(self):
		"""Test CRM interaction ticket creation, SLA calculation, resolution and closing (Chapter 4)."""
		# Ensure client exists
		inv_id = "__TEST_CM88012345XYZ"
		if not frappe.db.exists("Asset Investor", inv_id):
			self.test_03_standard_retail_individual_onboarding_lifecycle()

		ci = frappe.new_doc("Asset Client Interaction")
		ci.date_opened = now_datetime()
		ci.investor = inv_id
		ci.channel = "Phone Call"
		ci.sla_setup = "SLA_STATEMENT"
		ci.subject = "__TEST_ Request for Q3 Portfolio Valuation Statement"
		ci.description = "Client requested certified copy of Unit Trust statement for audit."
		ci.priority = "Medium"
		ci.assigned_to = "Administrator"
		ci.insert(ignore_permissions=True)

		self.assertEqual(ci.status, "Open")
		self.assertEqual(ci.investor_name, "Jane Mukasa")
		self.assertIsNotNone(ci.target_due_datetime)
		self.assertEqual(ci.is_overdue, 0)

		# 1. Resolve Case
		res = ci.resolve_case(resolution_summary="Emailed signed PDF portfolio valuation statement.")
		self.assertEqual(res["status"], "Resolved")
		self.assertEqual(ci.status, "Resolved")
		self.assertIsNotNone(ci.resolution_datetime)

		# 2. Close Case with Positive Feedback
		cl = ci.close_case(client_feedback="Satisfied", feedback_comments="Fast turnaround within 1 hour.")
		self.assertEqual(cl["status"], "Closed")
		self.assertEqual(ci.status, "Closed")
		self.assertEqual(ci.client_feedback, "Satisfied")

		# 3. Reopen Case on Dissatisfaction (Chapter 4.5)
		ro = ci.reopen_case(reason="Client called back stating page 2 was missing.")
		self.assertEqual(ro["status"], "In Progress")
		self.assertEqual(ro["escalation_level"], "Level 2 (Team Leader)")
		self.assertEqual(ci.client_feedback, "Dissatisfied")

	def test_08_crm_sla_breach_detection(self):
		"""Verify automated SLA breach detection and escalation when target due date passes (Chapter 4.6)."""
		inv_id = "__TEST_CM88012345XYZ"
		ci = frappe.new_doc("Asset Client Interaction")
		ci.date_opened = add_to_date(now_datetime(), hours=-5)  # opened 5 hours ago
		ci.investor = inv_id
		ci.channel = "Email"
		ci.sla_setup = "SLA_STATEMENT"  # SLA = 2 hours!
		ci.subject = "__TEST_ Delayed Statement SLA Breach Simulation"
		ci.description = "Test SLA monitor breach"
		ci.insert(ignore_permissions=True)

		ci.reload()
		# Since 5 hours elapsed on a 2-hour SLA, target_due_datetime is past
		self.assertEqual(ci.is_overdue, 1)
		self.assertEqual(ci.status, "Escalated")
		self.assertEqual(ci.escalation_level, "Level 2 (Team Leader)")

	def test_09_suspicious_transaction_log_tracking(self):
		"""Verify AML compliance logging for transactions exceeding regulatory thresholds (Chapter 3.7)."""
		inv_id = "__TEST_CM88012345XYZ"
		log = frappe.new_doc("Asset Suspicious Transaction Log")
		log.log_date = nowdate()
		log.rule = "AML_LARGE_CASH"
		log.investor = inv_id
		log.transaction_reference = "DEP-UGX-2026-00099"
		log.amount = 50000000.0  # 50 Million UGX
		log.status = "Open"
		log.investigation_notes = "Large cash deposit via Flexipay. KYC refreshed and verified."
		log.insert(ignore_permissions=True)

		self.assertEqual(log.status, "Open")
		self.assertEqual(log.amount, 50000000.0)

		# Compliance Officer reviews and clears
		log.reviewed_by = "Administrator"
		log.review_date = nowdate()
		log.status = "Cleared"
		log.action_taken = "Cleared without SAR"
		log.save(ignore_permissions=True)

		self.assertEqual(log.status, "Cleared")

	def test_10_expiring_kyc_monitoring_on_investor(self):
		"""Verify client KYC expiry detection and status update (Chapter 3.4)."""
		inv_id = "__TEST_CM88012345XYZ"
		investor = frappe.get_doc("Asset Investor", inv_id)

		# Set one KYC document as expired in the past
		kyc_docs = frappe.get_all("Asset Investor KYC Document", filters={"investor": inv_id})
		if kyc_docs:
			frappe.db.set_value(
				"Asset Investor KYC Document", kyc_docs[0].name, {"expiry_date": add_days(nowdate(), -10)}
			)

		summary = investor.get_kyc_status_summary()
		self.assertTrue(summary["has_expired"])
		investor.reload()
		self.assertEqual(investor.kyc_status, "Pending")


if __name__ == "__main__":
	unittest.main()
