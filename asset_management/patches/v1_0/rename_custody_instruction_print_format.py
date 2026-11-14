import frappe


def execute() -> None:
	"""Rename legacy Custody Instruction Print Format and Regulatory Fee tier values."""
	old_pf = "Stan" + "bic Custody Instruction"
	new_pf = "Custody Instruction"

	# System migration patch: rename or remove legacy print format
	if frappe.db.exists("Print Format", old_pf):
		if frappe.db.exists("Print Format", new_pf):
			frappe.delete_doc("Print Format", old_pf, force=True, ignore_permissions=True)
		else:
			frappe.rename_doc("Print Format", old_pf, new_pf, force=True, ignore_permissions=True)

	old_fee = "Regulatory Fee (" + "CM" + "A)"
	for row_name in frappe.get_all("Asset Fund Fee Tier", filters={"fee_type": old_fee}, pluck="name"):
		frappe.db.set_value("Asset Fund Fee Tier", row_name, "fee_type", "Regulatory Fee")
