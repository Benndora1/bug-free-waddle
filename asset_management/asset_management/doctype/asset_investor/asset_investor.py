import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate, getdate

class AssetInvestor(Document):
    def get_kyc_status_summary(self):
        """Checks for expiring or expired KYC documents (Chapter 3.4)."""
        docs = frappe.get_all(
            "Asset Investor KYC Document",
            filters={"investor": self.name},
            fields=["document_code", "document_name", "verification_status", "expiry_date"]
        )
        has_expired = False
        today = getdate(nowdate())
        for d in docs:
            if d.expiry_date and getdate(d.expiry_date) < today:
                has_expired = True
                if d.verification_status != "Expired":
                    frappe.db.set_value("Asset Investor KYC Document", d.name, "verification_status", "Expired")

        if has_expired:
            self.kyc_status = "Pending"
            self.db_set("kyc_status", "Pending")

        return {
            "total_documents": len(docs),
            "has_expired": has_expired,
            "documents": docs
        }

    def update_portfolio_balance(self, total_value, total_units):
        """Updates client net asset value and unit count from valuation engine."""
        self.total_portfolio_value = total_value
        self.total_units_held = total_units
        self.db_set("total_portfolio_value", total_value)
        self.db_set("total_units_held", total_units)
