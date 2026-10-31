import frappe
from asset_management.asset_management.portal_api import get_investor_holdings, get_resolved_investor

def get_context(context):
    investor_name = frappe.form_dict.get("investor") or get_resolved_investor()
    data = get_investor_holdings(investor_name)

    context.active_page = "holdings"
    context.investor = data.get("investor", {})
    context.portfolios = data.get("portfolios", [])
    context.total_value = data.get("total_value", 0.0)
    context.total_units = data.get("total_units", 0.0)
