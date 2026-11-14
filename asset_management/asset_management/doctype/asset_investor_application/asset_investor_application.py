import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, add_years, now_datetime, nowdate


class AssetInvestorApplication(Document):
	def validate(self):
		if not self.status:
			self.status = "Draft"
		self.calculate_risk_score()

	def calculate_risk_score(self):
		"""Calculates AML/KYC risk score and determines EDD requirement (Chapter 3 / Procedure Manual 4.1.18)."""
		score = 0.0

		# 1. Investor Type & Category
		if self.client_category == "Retail":
			score += 5.0
		elif self.client_category == "High Net Worth":
			score += 20.0
		elif self.client_category in ("Institutional", "Pension Fund"):
			score += 15.0

		if self.investor_type in ("Corporate", "Trust / Institutional"):
			score += 15.0

		# 2. Country of Residence
		if self.country_of_residence and self.country_of_residence != "Uganda":
			score += 15.0

		# 3. PEP Screening
		if self.pep_status == "Yes":
			score += 45.0
		elif self.pep_status == "Associated":
			score += 25.0

		# 4. Sanctions Screening
		if self.sanction_status == "Yes":
			score += 50.0

		# Check Signatories PEP
		if self.signatories:
			for sig in self.signatories:
				if sig.pep_status == "Yes":
					score += 30.0
					self.pep_status = "Associated"
					break

		self.risk_score = round(score, 2)

		# Determine Tier
		if self.risk_score <= 30.0:
			self.risk_tier = "Low"
		elif self.risk_score <= 60.0:
			self.risk_tier = "Medium"
		else:
			self.risk_tier = "High"

		# Mandatory Enhanced Due Diligence (EDD) if High Risk or PEP
		if (
			self.risk_tier == "High"
			or self.pep_status in ("Yes", "Associated")
			or self.sanction_status == "Yes"
		):
			self.edd_required = 1
		else:
			self.edd_required = 0

	@frappe.whitelist()
	def load_required_documents(self):
		"""Loads and links required KYC documents based on investor type (User Manual Chapter 2.2)."""
		req_docs = frappe.get_all(
			"Asset Required Document",
			filters={"investor_type": ["in", [self.investor_type, "All"]]},
			fields=["document_code", "document_name", "mandatory"],
		)
		created_count = 0
		for rd in req_docs:
			exists = frappe.db.exists(
				"Asset Investor KYC Document",
				{"parent_application": self.name, "document_code": rd.document_code},
			)
			if not exists:
				doc = frappe.new_doc("Asset Investor KYC Document")
				doc.document_code = rd.document_code
				doc.document_name = rd.document_name
				doc.parent_application = self.name
				doc.verification_status = "Pending"
				doc.insert(ignore_permissions=True)
				created_count += 1

		return {"total_required": len(req_docs), "newly_added": created_count}

	@frappe.whitelist()
	def run_verification_checks(self):
		"""Runs PEP and Sanctions background checks, calculates risk score (User Manual Chapter 2.2)."""
		self.calculate_risk_score()
		self.save(ignore_permissions=True)
		return {"risk_score": self.risk_score, "risk_tier": self.risk_tier, "edd_required": self.edd_required}

	def before_submit(self):
		"""Validates mandatory KYC documents and CE approval before submission."""
		# 1. Verify Mandatory KYC Documents
		req_mandatory = frappe.get_all(
			"Asset Required Document",
			filters={"investor_type": ["in", [self.investor_type, "All"]], "mandatory": 1},
			pluck="document_code",
		)
		for code in req_mandatory:
			kyc_rec = frappe.get_all(
				"Asset Investor KYC Document",
				filters={"parent_application": self.name, "document_code": code},
				fields=["verification_status", "attachment"],
			)
			if not kyc_rec:
				frappe.throw(
					_(
						"Mandatory KYC Document '{0}' has not been loaded or provided for application {1}."
					).format(code, self.name)
				)
			if not kyc_rec[0].attachment:
				frappe.throw(
					_("Mandatory KYC Document '{0}' does not have any attached file uploaded.").format(code)
				)

		# 2. Strict CE Approval Rule for High-Risk & PEP Investors (Procedure Manual 4.1.18 & 4.2.9)
		if self.edd_required and not self.approved_by_ce:
			frappe.throw(
				_(
					"Application {0} is classified as High Risk / PEP. Operational regulations require explicit approval by the Chief Executive (approved_by_ce = 1) before submission."
				).format(self.name)
			)

	def on_submit(self):
		"""Approves the application and creates the Asset Investor Master (Chapter 2.3)."""
		# 3. Create or Update Asset Investor Master Record
		investor_id = self.identification_no.strip().upper()
		if not investor_id:
			investor_id = f"INV-{self.name[-5:]}"

		if frappe.db.exists("Asset Investor", investor_id):
			investor = frappe.get_doc("Asset Investor", investor_id)
		else:
			investor = frappe.new_doc("Asset Investor")
			investor.investor_id = investor_id

		investor.investor_name = self.investor_name
		investor.investor_type = self.investor_type
		investor.client_category = self.client_category
		investor.email = self.email
		investor.phone = self.phone
		investor.tax_id = self.tax_id
		investor.country_of_residence = self.country_of_residence
		investor.status = "Active"
		investor.kyc_status = "Verified"
		investor.pep_status = self.pep_status
		investor.sanction_status = self.sanction_status
		investor.risk_tier = self.risk_tier
		investor.verified_date = nowdate()
		investor.last_review_date = nowdate()
		investor.next_review_date = add_months(
			nowdate(), 6 if self.risk_tier == "High" else (12 if self.risk_tier == "Medium" else 24)
		)
		investor.created_from_application = self.name

		# Settlement Bank Details
		investor.bank_name = self.bank_name
		investor.bank_branch = self.bank_branch
		investor.bank_account_name = self.bank_account_name
		investor.bank_account_no = self.bank_account_no
		investor.settlement_currency = self.settlement_currency or "UGX"

		investor.save(ignore_permissions=True)

		# Update application state
		self.created_investor_account = investor.investor_id
		self.status = "Approved"
		self.approval_date = nowdate()
		self.reviewed_by = frappe.session.user
		self.db_set("created_investor_account", investor.investor_id)
		self.db_set("status", "Approved")
		self.db_set("approval_date", nowdate())
		self.db_set("reviewed_by", frappe.session.user)

		# Link uploaded KYC documents to the created investor
		frappe.db.sql(
			"""UPDATE `tabAsset Investor KYC Document`
               SET investor = %s
               WHERE parent_application = %s""",
			(investor.investor_id, self.name),
		)

		frappe.msgprint(
			_("Asset Investor Account '{0}' successfully created and activated.").format(investor.investor_id)
		)

	def on_cancel(self):
		"""Cancels application and suspends client if already created."""
		self.status = "Rejected"
		self.db_set("status", "Rejected")
		if self.created_investor_account and frappe.db.exists(
			"Asset Investor", self.created_investor_account
		):
			investor = frappe.get_doc("Asset Investor", self.created_investor_account)
			investor.status = "Suspended"
			investor.save(ignore_permissions=True)
