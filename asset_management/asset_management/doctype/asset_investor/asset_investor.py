import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class AssetInvestor(Document):
	def get_kyc_status_summary(self):
		"""Checks for expiring or expired KYC documents (Chapter 3.4)."""
		docs = frappe.get_all(
			"Asset Investor KYC Document",
			filters={"investor": self.name},
			fields=["document_code", "document_name", "verification_status", "expiry_date"],
		)
		has_expired = False
		today = getdate(nowdate())
		for d in docs:
			if d.expiry_date and getdate(d.expiry_date) < today:
				has_expired = True
				if d.verification_status != "Expired":
					frappe.db.set_value(
						"Asset Investor KYC Document", d.name, "verification_status", "Expired"
					)

		if has_expired:
			self.kyc_status = "Pending"
			self.db_set("kyc_status", "Pending")

		return {"total_documents": len(docs), "has_expired": has_expired, "documents": docs}

	def update_portfolio_balance(self, total_value, total_units):
		"""Updates client net asset value and unit count from valuation engine."""
		self.total_portfolio_value = total_value
		self.total_units_held = total_units
		self.db_set("total_portfolio_value", total_value)
		self.db_set("total_units_held", total_units)


def get_or_create_investor_supplier(investor_name: str) -> str:
	"""Ensures a 1:1 linked Supplier exists in Supplier Group 'Unit Holders' per ADR-0002."""
	if not investor_name:
		frappe.throw(_("Investor is required to resolve Supplier."))

	inv = frappe.get_doc("Asset Investor", investor_name)
	if inv.supplier and frappe.db.exists("Supplier", inv.supplier):
		return inv.supplier

	sname = inv.investor_name or inv.name
	if frappe.db.exists("Supplier", sname):
		inv.supplier = sname
		inv.db_set("supplier", sname)
		return sname

	# Ensure Supplier Group "Unit Holders" exists
	group_name = "Unit Holders"
	if not frappe.db.exists("Supplier Group", group_name):
		sg = frappe.new_doc("Supplier Group")
		sg.supplier_group_name = group_name
		sg.insert(ignore_permissions=True)

	# Create Supplier
	supplier_doc = frappe.new_doc("Supplier")
	supplier_doc.supplier_name = inv.investor_name or inv.name
	supplier_doc.supplier_group = group_name
	supplier_doc.supplier_type = (
		"Individual" if getattr(inv, "investor_type", None) == "Individual" else "Company"
	)
	supplier_doc.country = getattr(inv, "country_of_residence", None) or "Uganda"
	supplier_doc.insert(ignore_permissions=True)

	inv.supplier = supplier_doc.name
	inv.db_set("supplier", supplier_doc.name)
	return supplier_doc.name
