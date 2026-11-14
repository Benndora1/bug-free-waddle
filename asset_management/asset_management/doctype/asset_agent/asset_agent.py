import frappe
from frappe.model.document import Document


class AssetAgent(Document):
	pass


def get_or_create_agent_supplier(agent_code: str) -> str:
	"""Resolves or creates a 1:1 linked Supplier for distribution commission payouts."""
	agent_doc = frappe.get_doc("Asset Agent", agent_code)
	supplier = getattr(agent_doc, "supplier", None)
	if supplier and frappe.db.exists("Supplier", supplier):
		return supplier

	sname = agent_doc.agent_name or agent_code
	if frappe.db.exists("Supplier", sname):
		return sname

	sup = frappe.new_doc("Supplier")
	sup.supplier_name = sname
	sup.supplier_group = "Services"
	sup.supplier_type = "Individual" if agent_doc.agent_type == "Individual" else "Company"
	sup.insert(ignore_permissions=True)
	return sup.name
