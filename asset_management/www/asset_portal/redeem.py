import frappe
from asset_management.asset_management.portal_api import get_investor_holdings, get_resolved_investor

def get_context(context):
    investor_name = frappe.form_dict.get("investor") or get_resolved_investor()
    data = get_investor_holdings(investor_name)

    context.active_page = "redeem"
    context.investor = data.get("investor", {})
    context.portfolios = [p for p in data.get("portfolios", []) if (p.get("total_units") or 0) > 0]
    context.preselected_fund = frappe.form_dict.get("fund") or ""
