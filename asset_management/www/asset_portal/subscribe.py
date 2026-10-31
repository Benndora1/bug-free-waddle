import frappe
from asset_management.asset_management.portal_api import get_investor_dashboard, get_resolved_investor

def get_context(context):
    investor_name = frappe.form_dict.get("investor") or get_resolved_investor()
    data = get_investor_dashboard(investor_name)

    context.active_page = "subscribe"
    context.investor = data.get("investor", {})
    context.funds = frappe.get_all(
        "Asset Fund",
        filters={"status": "Active"},
        fields=["fund_id", "fund_name", "fund_type", "currency", "min_subscription_amount", "min_additional_amount", "current_offer_price"]
    )
    context.preselected_fund = frappe.form_dict.get("fund") or ""
