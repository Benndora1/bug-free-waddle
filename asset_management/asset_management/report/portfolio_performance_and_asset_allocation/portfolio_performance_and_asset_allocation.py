import frappe
from frappe import _

def execute(filters=None):
    columns = [
        {"label": _("Fund"), "fieldname": "fund", "fieldtype": "Link", "options": "Asset Fund", "width": 100},
        {"label": _("Security ID"), "fieldname": "security", "fieldtype": "Link", "options": "Asset Investment Security", "width": 130},
        {"label": _("Asset Class"), "fieldname": "asset_class", "fieldtype": "Data", "width": 130},
        {"label": _("Face Value / Shares"), "fieldname": "face_value", "fieldtype": "Currency", "width": 140},
        {"label": _("Carrying Cost"), "fieldname": "carrying_cost", "fieldtype": "Currency", "width": 140},
        {"label": _("Accrued Interest"), "fieldname": "accrued_interest", "fieldtype": "Currency", "width": 120},
        {"label": _("Market Value"), "fieldname": "dirty_market_value", "fieldtype": "Currency", "width": 140},
        {"label": _("Yield / XIRR %"), "fieldname": "xirr", "fieldtype": "Percent", "width": 100},
        {"label": _("Status"), "fieldname": "holding_status", "fieldtype": "Data", "width": 90}
    ]

    conditions = {}
    if filters and filters.get("fund"):
        conditions["fund"] = filters.get("fund")

    data = frappe.get_all(
        "Asset Portfolio Holding",
        filters=conditions,
        fields=[
            "fund", "security", "asset_class", "face_value",
            "carrying_cost", "accrued_interest", "dirty_market_value",
            "xirr", "holding_status"
        ],
        order_by="fund, dirty_market_value desc"
    )

    return columns, data
