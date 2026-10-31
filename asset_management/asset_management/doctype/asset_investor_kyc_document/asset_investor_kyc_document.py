import frappe
from frappe.model.document import Document
from frappe.utils import nowdate

class AssetInvestorKYCDocument(Document):
    def validate(self):
        if self.verification_status == "Verified" and not self.verified_by:
            self.verified_by = frappe.session.user
            self.verification_date = nowdate()

        if self.investor and self.verification_status == "Verified":
            frappe.db.set_value("Asset Investor", self.investor, {
                "kyc_status": "Verified",
                "verified_date": nowdate()
            })
