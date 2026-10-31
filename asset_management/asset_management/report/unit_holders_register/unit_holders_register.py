import frappe
from frappe import _

def execute(filters=None):
    columns = [
        {"label": _("Fund Code"), "fieldname": "fund", "fieldtype": "Link", "options": "Asset Fund", "width": 100},
        {"label": _("Investor ID"), "fieldname": "investor", "fieldtype": "Link", "options": "Asset Investor", "width": 120},
        {"label": _("Investor Name"), "fieldname": "investor_name", "fieldtype": "Data", "width": 180},
        {"label": _("Total Units"), "fieldname": "total_units", "fieldtype": "Float", "width": 120},
        {"label": _("NAV / Unit"), "fieldname": "current_nav_per_unit", "fieldtype": "Currency", "width": 110},
        {"label": _("Market Value"), "fieldname": "current_market_value", "fieldtype": "Currency", "width": 140},
        {"label": _("Total Subscriptions"), "fieldname": "total_invested_amount", "fieldtype": "Currency", "width": 140},
        {"label": _("Total Redemptions"), "fieldname": "total_withdrawn_amount", "fieldtype": "Currency", "width": 130},
        {"label": _("Unrealized Gain/Loss"), "fieldname": "unrealized_gain_loss", "fieldtype": "Currency", "width": 140},
        {"label": _("Status"), "fieldname": "portfolio_status", "fieldtype": "Data", "width": 90}
    ]

    conditions = {}
    if filters and filters.get("fund"):
        conditions["fund"] = filters.get("fund")
    if filters and filters.get("investor"):
        conditions["investor"] = filters.get("investor")

    data = frappe.get_all(
        "Asset Investor Portfolio",
        filters=conditions,
        fields=[
            "fund", "investor", "investor_name", "total_units",
            "current_nav_per_unit", "current_market_value",
            "total_invested_amount", "total_withdrawn_amount",
            "unrealized_gain_loss", "portfolio_status"
        ],
        order_by="fund, total_units desc"
    )

    return columns, data
