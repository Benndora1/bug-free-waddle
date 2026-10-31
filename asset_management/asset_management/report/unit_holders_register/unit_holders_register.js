frappe.query_reports["Unit Holders Register"] = {
    "filters": [
        {"fieldname": "fund", "label": __("Fund"), "fieldtype": "Link", "options": "Asset Fund"},
        {"fieldname": "investor", "label": __("Investor"), "fieldtype": "Link", "options": "Asset Investor"}
    ]
};