frappe.query_reports["Daily Fund Valuation Summary"] = {
    "filters": [
        {"fieldname": "fund", "label": __("Fund"), "fieldtype": "Link", "options": "Asset Fund"}
    ]
};