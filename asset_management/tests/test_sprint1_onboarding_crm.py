"""Integration tests for investor onboarding, KYC, risk scoring, and CRM SLA (Sprint 1)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from asset_management.tests.factories import make_fund


class TestSprint1OnboardingCRM(IntegrationTestCase):
	def _create_approved_retail_investor(self, ident_no: str = "__TEST_ID_88012345") -> str:
		if frappe.db.exists("Asset Investor", ident_no):
			return ident_no

		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.onboarding_channel = "Face to Face"
		app.investor_type = "Individual"
		app.client_category = "Retail"
		app.investor_name = "Jane Citizen"
		app.identification_type = "National ID"
		app.identification_no = ident_no
		app.tax_id = "1002345678"
		app.country_of_residence = "United States"
		app.email = "jane.citizen@example.com"
		app.phone = "+15551234567"
		app.physical_address = "100 Main Street, Suite 200"
		app.bank_name = "First Commercial Bank"
		app.bank_branch = "Main Branch"
		app.bank_account_name = "Jane Citizen"
		app.bank_account_no = "9030012345678"
		app.settlement_currency = "USD"
		app.pep_status = "No"
		app.sanction_status = "No"
		# Test setup: ignore_permissions required
		app.insert(ignore_permissions=True)

		app.load_required_documents()
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

		app.run_verification_checks()
		app.reload()
		app.submit()
		return app.created_investor_account

	def test_03_standard_retail_individual_onboarding_lifecycle(self) -> None:
		"""Test full onboarding lifecycle for a standard low-risk retail investor."""
		ident_no = "__TEST_ID_RETAIL_01"
		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.onboarding_channel = "Face to Face"
		app.investor_type = "Individual"
		app.client_category = "Retail"
		app.investor_name = "Jane Citizen"
		app.identification_type = "National ID"
		app.identification_no = ident_no
		app.tax_id = "1002345678"
		app.country_of_residence = "United States"
		app.email = "jane.citizen@example.com"
		app.phone = "+15551234567"
		app.physical_address = "100 Main Street, Suite 200"
		app.bank_name = "First Commercial Bank"
		app.bank_branch = "Main Branch"
		app.bank_account_name = "Jane Citizen"
		app.bank_account_no = "9030012345678"
		app.settlement_currency = "USD"
		app.pep_status = "No"
		app.sanction_status = "No"
		# Test setup: ignore_permissions required
		app.insert(ignore_permissions=True)

		self.assertEqual(app.status, "Draft")

		res_docs = app.load_required_documents()
		self.assertGreater(res_docs["total_required"], 0)

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

		chk = app.run_verification_checks()
		self.assertLessEqual(chk["risk_score"], 30.0)
		self.assertEqual(chk["risk_tier"], "Low")
		self.assertEqual(chk["edd_required"], 0)

		app.reload()
		app.submit()

		self.assertEqual(app.status, "Approved")
		self.assertEqual(app.created_investor_account, ident_no)

		self.assertTrue(frappe.db.exists("Asset Investor", ident_no))
		investor = frappe.get_doc("Asset Investor", ident_no)
		self.assertEqual(investor.investor_name, "Jane Citizen")
		self.assertEqual(investor.status, "Active")
		self.assertEqual(investor.risk_tier, "Low")
		self.assertEqual(investor.bank_account_no, "9030012345678")

	def test_04_high_risk_and_pep_application_requires_ce_approval(self) -> None:
		"""Verify strict regulatory rule: High-risk/PEP applicants require CE sign-off before approval."""
		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.onboarding_channel = "Wholesale / Direct"
		app.investor_type = "Individual"
		app.client_category = "High Net Worth"
		app.investor_name = "Hon. Peter Sterling"
		app.identification_type = "Passport"
		app.identification_no = "__TEST_P88990011"
		app.tax_id = "1009988776"
		app.country_of_residence = "United States"
		app.email = "peter.sterling@example.com"
		app.phone = "+15550199887"
		app.physical_address = "500 Embassy Row"
		app.bank_name = "First Commercial Bank"
		app.bank_branch = "Private Banking Branch"
		app.bank_account_name = "Peter Sterling"
		app.bank_account_no = "9030088990011"
		app.pep_status = "Yes"
		app.sanction_status = "No"
		# Test setup: ignore_permissions required
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

		app.reload()
		app.approved_by_ce = 0
		with self.assertRaises(frappe.ValidationError):
			app.submit()

		app = frappe.get_doc("Asset Investor Application", app.name)
		app.approved_by_ce = 1
		app.edd_notes = "EDD conducted. Sources of funds verified. CE approved."
		app.submit()

		self.assertEqual(app.status, "Approved")
		self.assertTrue(frappe.db.exists("Asset Investor", "__TEST_P88990011"))
		investor = frappe.get_doc("Asset Investor", "__TEST_P88990011")
		self.assertEqual(investor.pep_status, "Yes")
		self.assertEqual(investor.risk_tier, "High")

	def test_05_mandatory_kyc_missing_attachment_guard(self) -> None:
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
		app.phone = "+15550001111"
		app.physical_address = "200 Oak Street"
		app.bank_name = "First Commercial Bank"
		app.bank_branch = "Main Branch"
		app.bank_account_name = "Missing Doc"
		app.bank_account_no = "9030011122233"
		# Test setup: ignore_permissions required
		app.insert(ignore_permissions=True)

		app.load_required_documents()
		app.reload()
		with self.assertRaises(frappe.ValidationError):
			app.submit()

	def test_06_corporate_application_with_signatories_and_beneficiaries(self) -> None:
		"""Test Corporate onboarding with multiple directors and Next of Kin beneficiaries."""
		app = frappe.new_doc("Asset Investor Application")
		app.application_date = nowdate()
		app.investor_type = "Corporate"
		app.client_category = "Institutional"
		app.investor_name = "Horizon Agri Holdings Ltd"
		app.identification_type = "Certificate of Incorporation"
		app.identification_no = "__TEST_CORP_800123"
		app.tax_id = "5000123456"
		app.country_of_residence = "United States"
		app.email = "info@horizonagri.example.com"
		app.phone = "+15554141234"
		app.physical_address = "7th Avenue Industrial Park"
		app.bank_name = "First Commercial Bank"
		app.bank_branch = "Corporate Branch"
		app.bank_account_name = "Horizon Agri Holdings Ltd"
		app.bank_account_no = "9030099881122"

		app.append(
			"signatories",
			{
				"full_name": "Dr. Sarah Carter",
				"signatory_type": "Director",
				"identification_type": "National ID",
				"identification_no": "ID70011122",
				"phone": "+15559990001",
				"pep_status": "No",
			},
		)
		app.append(
			"signatories",
			{
				"full_name": "James Miller",
				"signatory_type": "Authorized Signatory",
				"identification_type": "National ID",
				"identification_no": "ID75022233",
				"phone": "+15558881112",
				"pep_status": "No",
			},
		)
		app.append(
			"beneficiaries",
			{
				"full_name": "Horizon Employee Trust Scheme",
				"relationship": "Trustee",
				"allocation_percent": 100.0,
				"phone": "+15554141234",
			},
		)

		# Test setup: ignore_permissions required
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

	def test_07_crm_client_interaction_lifecycle(self) -> None:
		"""Test CRM interaction ticket creation, SLA calculation, resolution and closing."""
		inv_id = self._create_approved_retail_investor()

		ci = frappe.new_doc("Asset Client Interaction")
		ci.date_opened = now_datetime()
		ci.investor = inv_id
		ci.channel = "Phone Call"
		ci.sla_setup = "SLA_STATEMENT"
		ci.subject = "__TEST_ Request for Q3 Portfolio Valuation Statement"
		ci.description = "Client requested certified copy of Unit Trust statement for audit."
		ci.priority = "Medium"
		ci.assigned_to = "Administrator"
		# Test setup: ignore_permissions required
		ci.insert(ignore_permissions=True)

		self.assertEqual(ci.status, "Open")
		self.assertEqual(ci.investor_name, "Jane Citizen")
		self.assertIsNotNone(ci.target_due_datetime)
		self.assertEqual(ci.is_overdue, 0)

		res = ci.resolve_case(resolution_summary="Emailed signed PDF portfolio valuation statement.")
		self.assertEqual(res["status"], "Resolved")
		self.assertEqual(ci.status, "Resolved")
		self.assertIsNotNone(ci.resolution_datetime)

		cl = ci.close_case(client_feedback="Satisfied", feedback_comments="Fast turnaround within 1 hour.")
		self.assertEqual(cl["status"], "Closed")
		self.assertEqual(ci.status, "Closed")
		self.assertEqual(ci.client_feedback, "Satisfied")

		ro = ci.reopen_case(reason="Client called back stating page 2 was missing.")
		self.assertEqual(ro["status"], "In Progress")
		self.assertEqual(ro["escalation_level"], "Level 2 (Team Leader)")
		self.assertEqual(ci.client_feedback, "Dissatisfied")

	def test_08_crm_sla_breach_detection(self) -> None:
		"""Verify automated SLA breach detection and escalation when target due date passes."""
		inv_id = self._create_approved_retail_investor()
		ci = frappe.new_doc("Asset Client Interaction")
		ci.date_opened = add_to_date(now_datetime(), hours=-5)
		ci.investor = inv_id
		ci.channel = "Email"
		ci.sla_setup = "SLA_STATEMENT"
		ci.subject = "__TEST_ Delayed Statement SLA Breach Simulation"
		ci.description = "Test SLA monitor breach"
		# Test setup: ignore_permissions required
		ci.insert(ignore_permissions=True)

		ci.reload()
		self.assertEqual(ci.is_overdue, 1)
		self.assertEqual(ci.status, "Escalated")
		self.assertEqual(ci.escalation_level, "Level 2 (Team Leader)")

	def test_09_suspicious_transaction_log_tracking(self) -> None:
		"""Verify automated AML compliance logging from 48-hour unallocated BOL deposits and compliance clearance."""
		fund = make_fund(fund_id="TEST-AML-MMF", fund_name="Test AML Money Market Fund")
		bol = frappe.new_doc("Asset BOL Import Header")
		bol.file_name = "BOL_AML_TEST.csv"
		bol.bank_name = "First Commercial Bank"
		bol.bank_account_no = "901000223344"
		# Test setup: ignore_permissions required
		bol.insert(ignore_permissions=True)

		three_days_ago = add_days(nowdate(), -3)
		bol.append(
			"lines",
			{
				"line_no": 1,
				"value_date": three_days_ago,
				"transaction_description": "Unidentified wire transfer ref 778899",
				"amount": 50000000.0,
				"fund_code": fund.name,
				"status": "Exception",
				"exception_reason": "No client match found",
				"unallocated_since": three_days_ago,
			},
		)
		# Test setup: ignore_permissions required
		bol.save(ignore_permissions=True)

		res = bol.check_unallocated_sla(threshold_hours=48.0)
		self.assertEqual(res["escalated_count"], 1)

		ref = f"{bol.name}-1"
		log = frappe.get_doc("Asset Suspicious Transaction Log", {"transaction_reference": ref})
		self.assertEqual(log.rule, "AML_UNALLOCATED")
		self.assertEqual(log.amount, 50000000.0)
		self.assertEqual(log.status, "Investigating")

		log.reviewed_by = "Administrator"
		log.review_date = nowdate()
		log.status = "Cleared"
		log.action_taken = "Cleared without SAR"
		# Test setup: ignore_permissions required
		log.save(ignore_permissions=True)
		self.assertEqual(log.status, "Cleared")

	def test_10_expiring_kyc_monitoring_on_investor(self) -> None:
		"""Verify client KYC expiry detection and status update."""
		inv_id = self._create_approved_retail_investor()
		investor = frappe.get_doc("Asset Investor", inv_id)

		kyc_docs = frappe.get_all("Asset Investor KYC Document", filters={"investor": inv_id})
		self.assertGreater(len(kyc_docs), 0)
		frappe.db.set_value(
			"Asset Investor KYC Document", kyc_docs[0].name, {"expiry_date": add_days(nowdate(), -10)}
		)

		summary = investor.get_kyc_status_summary()
		self.assertTrue(summary["has_expired"])
		investor.reload()
		self.assertEqual(investor.kyc_status, "Pending")
