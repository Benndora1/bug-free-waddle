import frappe

from asset_management.asset_management.portal_api import get_investor_dashboard, get_resolved_investor


def get_context(context):
	investor_name = frappe.form_dict.get("investor") or get_resolved_investor()
	data = get_investor_dashboard(investor_name)

	context.active_page = "dashboard"
	context.investor = data.get("investor", {})
	context.total_value = data.get("total_value", 0.0)
	context.total_units = data.get("total_units", 0.0)
	context.total_invested = data.get("total_invested", 0.0)
	context.total_unrealized = data.get("total_unrealized", 0.0)
	context.portfolios = data.get("portfolios", [])
	context.recent_subscriptions = data.get("recent_subscriptions", [])
	context.recent_redemptions = data.get("recent_redemptions", [])
	context.market_funds = data.get("market_funds", [])
