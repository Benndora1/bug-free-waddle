import frappe
from frappe import _
from frappe.utils import nowdate, date_diff

def execute(filters=None):
    columns = [
        {"label": _("Security ID"), "fieldname": "security_id", "fieldtype": "Link", "options": "Asset Investment Security", "width": 130},
        {"label": _("Security Name"), "fieldname": "security_name", "fieldtype": "Data", "width": 200},
        {"label": _("Asset Class"), "fieldname": "asset_class", "fieldtype": "Data", "width": 130},
        {"label": _("Issuer"), "fieldname": "issuer", "fieldtype": "Data", "width": 160},
        {"label": _("Maturity Date"), "fieldname": "maturity_date", "fieldtype": "Date", "width": 110},
        {"label": _("Days to Maturity"), "fieldname": "days_to_maturity", "fieldtype": "Int", "width": 110},
        {"label": _("Coupon / Rate %"), "fieldname": "coupon_rate", "fieldtype": "Percent", "width": 110},
        {"label": _("Current Price"), "fieldname": "current_market_price", "fieldtype": "Float", "width": 100},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 90}
    ]

    conditions = {"status": "Active"}
    if filters and filters.get("asset_class"):
        conditions["asset_class"] = filters.get("asset_class")

    securities = frappe.get_all(
        "Asset Investment Security",
        filters=conditions,
        fields=[
            "security_id", "security_name", "asset_class", "issuer",
            "maturity_date", "coupon_rate", "current_market_price", "status"
        ],
        order_by="maturity_date asc"
    )

    data = []
    today = nowdate()
    for s in securities:
        dtm = date_diff(s.maturity_date, today) if s.maturity_date else 0
        s["days_to_maturity"] = max(0, dtm)
        data.append(s)

    return columns, data
