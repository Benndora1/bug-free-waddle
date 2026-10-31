import frappe
from asset_management.asset_management.portal_api import get_agent_dashboard, get_resolved_agent

def get_context(context):
    agent_code = frappe.form_dict.get("agent") or get_resolved_agent()
    data = get_agent_dashboard(agent_code)

    context.active_page = "dashboard"
    context.agent = data.get("agent", {})
    context.total_clients = data.get("total_clients", 0)
    context.total_commission_earned = data.get("total_commission_earned", 0.0)
    context.total_commission_paid = data.get("total_commission_paid", 0.0)
    context.commission_due = data.get("commission_due", 0.0)
    context.clients = data.get("clients", [])
    context.commissions = data.get("commissions", [])
