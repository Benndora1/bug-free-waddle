import frappe

def create_doctypes():
    def make_doctype(data):
        name = data.get("name")
        if frappe.db.exists("DocType", name):
            print(f"DocType '{name}' already exists. Skipping.")
            return
        doc = frappe.new_doc("DocType")
        doc.update(data)
        doc.custom = 0
        doc.insert(ignore_permissions=True)
        print(f"Created DocType: '{name}'")

    # 1. Fund Valuation Line (Child Table)
    val_line = {
        "name": "Fund Valuation Line",
        "module": "Asset Management",
        "istable": 1,
        "fields": [
            {"fieldname": "instrument", "fieldtype": "Link", "label": "Instrument", "options": "Financial Instrument", "reqd": 1, "in_list_view": 1},
            {"fieldname": "asset_type", "fieldtype": "Link", "label": "Asset Type", "options": "Asset Type", "in_list_view": 1},
            {"fieldname": "quantity", "fieldtype": "Float", "label": "Holding Units", "reqd": 1, "in_list_view": 1},
            {"fieldname": "market_price", "fieldtype": "Currency", "label": "Market Price", "reqd": 1, "in_list_view": 1},
            {"fieldname": "accrued_interest", "fieldtype": "Currency", "label": "Accrued Interest"},
            {"fieldname": "current_value", "fieldtype": "Currency", "label": "Total Valuation", "read_only": 1, "in_list_view": 1}
        ]
    }

    # 2. Fund Valuation (NAV Valuation Header)
    val_header = {
        "name": "Fund Valuation",
        "module": "Asset Management",
        "autoname": "naming_series:",
        "naming_rule": "By \"Naming Series\" field",
        "is_submittable": 1,
        "fields": [
            {"fieldname": "naming_series", "fieldtype": "Select", "label": "Series", "options": "VAL-.YYYY.-.#####", "default": "VAL-.YYYY.-.#####", "reqd": 1},
            {"fieldname": "portfolio", "fieldtype": "Link", "label": "Fund / Portfolio", "options": "Investment Portfolio", "reqd": 1},
            {"fieldname": "valuation_date", "fieldtype": "Date", "label": "Valuation Date", "default": "Today", "reqd": 1},
            {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Draft\nApproved\nRejected", "default": "Draft"},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "opening_nav", "fieldtype": "Currency", "label": "Opening NAV"},
            {"fieldname": "gross_nav", "fieldtype": "Currency", "label": "Gross NAV", "read_only": 1},
            {"fieldname": "total_expenses", "fieldtype": "Currency", "label": "Total Accrued Expenses", "default": 0},
            {"fieldname": "closing_nav", "fieldtype": "Currency", "label": "Closing Net Asset Value (NAV)", "read_only": 1},
            {"fieldname": "col_break_2", "fieldtype": "Column Break"},
            {"fieldname": "total_outstanding_units", "fieldtype": "Float", "label": "Total Outstanding Units", "reqd": 1},
            {"fieldname": "nav_per_unit", "fieldtype": "Currency", "label": "NAV Per Unit", "read_only": 1},

            {"fieldname": "sec_holdings", "fieldtype": "Section Break", "label": "Portfolio Holdings & Asset Breakdown"},
            {"fieldname": "valuation_lines", "fieldtype": "Table", "label": "Valuation Lines", "options": "Fund Valuation Line"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 1, "cancel": 1, "amend": 1},
            {"role": "All", "read": 1}
        ]
    }

    # 3. Dividend Declaration Line (Child Table)
    div_line = {
        "name": "Dividend Declaration Line",
        "module": "Asset Management",
        "istable": 1,
        "fields": [
            {"fieldname": "investor", "fieldtype": "Link", "label": "Investor", "options": "Asset Investor", "reqd": 1, "in_list_view": 1},
            {"fieldname": "units_held", "fieldtype": "Float", "label": "Units Held at Closure", "reqd": 1, "in_list_view": 1},
            {"fieldname": "gross_dividend", "fieldtype": "Currency", "label": "Gross Dividend", "read_only": 1, "in_list_view": 1},
            {"fieldname": "withholding_tax", "fieldtype": "Currency", "label": "WHT Deducted", "read_only": 1, "in_list_view": 1},
            {"fieldname": "net_dividend_payable", "fieldtype": "Currency", "label": "Net Dividend Payable", "read_only": 1, "in_list_view": 1}
        ]
    }

    # 4. Dividend Declaration
    dividend_decl = {
        "name": "Dividend Declaration",
        "module": "Asset Management",
        "autoname": "naming_series:",
        "naming_rule": "By \"Naming Series\" field",
        "is_submittable": 1,
        "fields": [
            {"fieldname": "naming_series", "fieldtype": "Select", "label": "Series", "options": "DIV-.YYYY.-.#####", "default": "DIV-.YYYY.-.#####", "reqd": 1},
            {"fieldname": "portfolio", "fieldtype": "Link", "label": "Portfolio / Fund", "options": "Investment Portfolio", "reqd": 1},
            {"fieldname": "declaration_date", "fieldtype": "Date", "label": "Declaration Date", "default": "Today", "reqd": 1},
            {"fieldname": "book_closure_date", "fieldtype": "Date", "label": "Book Closure Date", "reqd": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "payment_date", "fieldtype": "Date", "label": "Payment Date", "reqd": 1},
            {"fieldname": "dividend_per_unit", "fieldtype": "Currency", "label": "Dividend Rate Per Unit", "reqd": 1},
            {"fieldname": "withholding_tax_pct", "fieldtype": "Percent", "label": "WHT Rate %", "default": 10},
            {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Draft\nApproved\nPaid\nCancelled", "default": "Draft"},
            {"fieldname": "total_gross_dividend", "fieldtype": "Currency", "label": "Total Gross Dividend", "read_only": 1},
            {"fieldname": "total_net_dividend", "fieldtype": "Currency", "label": "Total Net Dividend Payable", "read_only": 1},

            {"fieldname": "sec_beneficiaries", "fieldtype": "Section Break", "label": "Investor Schedule & Entitlements"},
            {"fieldname": "dividend_lines", "fieldtype": "Table", "label": "Beneficiary Lines", "options": "Dividend Declaration Line"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 1, "cancel": 1, "amend": 1},
            {"role": "All", "read": 1}
        ]
    }

    for dt in [val_line, val_header, div_line, dividend_decl]:
        make_doctype(dt)

    frappe.db.commit()
    print("Asset Management Phase 2 DocTypes created!")

