import frappe

from asset_management.asset_management.portal_api import get_investor_statement, get_resolved_investor


def get_context(context):
	investor_name = frappe.form_dict.get("investor") or get_resolved_investor()
	fund = frappe.form_dict.get("fund")
	from_date = frappe.form_dict.get("from_date")
	to_date = frappe.form_dict.get("to_date")

	data = get_investor_statement(investor_name, from_date=from_date, to_date=to_date, fund=fund)

	context.active_page = "statement"
	context.investor = data.get("investor", {})
	context.lines = data.get("lines", [])
	context.filter_fund = fund
	context.from_date = from_date
	context.to_date = to_date

	# Fetch investor's funds for filter dropdown
	context.funds = frappe.get_all(
		"Asset Investor Portfolio", filters={"investor": investor_name}, fields=["fund", "fund_name"]
	)
