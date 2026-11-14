import frappe


def execute():
	"""Delete legacy, duplicate, and unreferenced orphan DocTypes."""
	legacy_doctypes = [
		# Child tables first
		"Fund Valuation Line",
		"Dividend Declaration Line",
		# Main doctypes
		"Fund Valuation",
		"Dividend Declaration",
		"Financial Instrument",
		"Investment Portfolio",
		"Investment Setup",
		"Instrument Type",
		"Instrument Category",
		"Instrument Price",
		"Asset Type",
		"Fund Fee Setup",
	]

	for dt in legacy_doctypes:
		if frappe.db.exists("DocType", dt):
			frappe.delete_doc("DocType", dt, force=True)
			print(f"Deleted legacy DocType: {dt}")
