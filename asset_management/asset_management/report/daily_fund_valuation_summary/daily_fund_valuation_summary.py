import frappe
from frappe import _


def execute(filters=None):
	columns = [
		{"label": _("Valuation Date"), "fieldname": "valuation_date", "fieldtype": "Date", "width": 110},
		{
			"label": _("Fund Code"),
			"fieldname": "fund",
			"fieldtype": "Link",
			"options": "Asset Fund",
			"width": 100,
		},
		{"label": _("Fund Name"), "fieldname": "fund_name", "fieldtype": "Data", "width": 180},
		{
			"label": _("Gross Asset Value (GAV)"),
			"fieldname": "total_gav",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": _("Accrued Expenses"),
			"fieldname": "total_accrued_expenses",
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"label": _("Net Asset Value (NAV)"),
			"fieldname": "total_nav",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": _("Units in Issue"),
			"fieldname": "total_units_in_issue",
			"fieldtype": "Float",
			"width": 120,
		},
		{"label": _("NAV / Unit"), "fieldname": "nav_per_unit", "fieldtype": "Currency", "width": 110},
		{"label": _("Offer Price"), "fieldname": "offer_price", "fieldtype": "Currency", "width": 110},
		{"label": _("Bid Price"), "fieldname": "bid_price", "fieldtype": "Currency", "width": 110},
		{"label": _("Daily Change %"), "fieldname": "daily_change_pct", "fieldtype": "Percent", "width": 100},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90},
	]

	conditions = {}
	if filters and filters.get("fund"):
		conditions["fund"] = filters.get("fund")

	data = frappe.get_all(
		"Asset Fund Valuation",
		filters=conditions,
		fields=[
			"valuation_date",
			"fund",
			"fund_name",
			"total_gav",
			"total_accrued_expenses",
			"total_nav",
			"total_units_in_issue",
			"nav_per_unit",
			"offer_price",
			"bid_price",
			"daily_change_pct",
			"status",
		],
		order_by="valuation_date desc, fund",
	)

	return columns, data
