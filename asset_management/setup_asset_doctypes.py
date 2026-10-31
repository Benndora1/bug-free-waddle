import frappe

def create_asset_doctypes():
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

    # 1. Investment Setup (Single)
    investment_setup = {
        "name": "Investment Setup",
        "module": "Asset Management",
        "custom": 0,
        "issingle": 1,
        "fields": [
            {"fieldname": "sec_general", "fieldtype": "Section Break", "label": "General Settings"},
            {"fieldname": "daily_valuation_path", "fieldtype": "Data", "label": "Daily Valuation Path"},
            {"fieldname": "investment_email_address", "fieldtype": "Data", "label": "Investment Email Address", "options": "Email"},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "portfolio_naming_series", "fieldtype": "Data", "label": "Portfolio Naming Series", "default": "PORT-.YYYY.-.#####"},
            {"fieldname": "instrument_naming_series", "fieldtype": "Data", "label": "Instrument Naming Series", "default": "INST-.#####"},
            {"fieldname": "bond_naming_series", "fieldtype": "Data", "label": "Bond Naming Series", "default": "BOND-.#####"},
            
            {"fieldname": "sec_taxes_levies", "fieldtype": "Section Break", "label": "Capital Market & Levies"},
            {"fieldname": "withholding_tax_percentage", "fieldtype": "Percent", "label": "Withholding Tax Percentage"},
            {"fieldname": "vat_percent", "fieldtype": "Percent", "label": "VAT Percent"},
            {"fieldname": "sec_percent", "fieldtype": "Percent", "label": "SEC Percent"},
            {"fieldname": "col_break_2", "fieldtype": "Column Break"},
            {"fieldname": "cscs_fixed_amount", "fieldtype": "Currency", "label": "CSCS Fixed Amount"},
            {"fieldname": "nse_percent", "fieldtype": "Percent", "label": "NSE Percent"},
            {"fieldname": "stamp_percent", "fieldtype": "Percent", "label": "Stamp Percent"},
            {"fieldname": "other_percent", "fieldtype": "Percent", "label": "Other Percent"},

            {"fieldname": "sec_gl_integration", "fieldtype": "Section Break", "label": "Accounting & Posting"},
            {"fieldname": "default_company", "fieldtype": "Link", "label": "Company", "options": "Company"},
            {"fieldname": "use_gl_for_valuation_expenses", "fieldtype": "Check", "label": "Use GL for Valuation Expenses", "default": 1},
            {"fieldname": "col_break_3", "fieldtype": "Column Break"},
            {"fieldname": "distribution_payable_account", "fieldtype": "Link", "label": "Distribution Payable Account", "options": "Account"},
            {"fieldname": "distribution_expense_account", "fieldtype": "Link", "label": "Distribution Expense Account", "options": "Account"}
        ],
        "permissions": [{"role": "System Manager", "read": 1, "write": 1}]
    }

    # 2. Asset Type
    asset_type = {
        "name": "Asset Type",
        "module": "Asset Management",
        "autoname": "field:code",
        "naming_rule": "By fieldname",
        "fields": [
            {"fieldname": "code", "fieldtype": "Data", "label": "Code", "reqd": 1, "unique": 1},
            {"fieldname": "description", "fieldtype": "Data", "label": "Description", "reqd": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "general_type", "fieldtype": "Select", "label": "General Type", "options": "\nEquity\nBond\nMoney Market\nREITS\nMortgage\nProperty\nTreasury Bills", "reqd": 1},
            {"fieldname": "stock_market_class", "fieldtype": "Select", "label": "Stock Market Class", "options": "Capital Markets\nBonds\nMoney Markets\nReal Estate\nTreasury Bills\nDerivatives"},
            {"fieldname": "day_count_convention", "fieldtype": "Select", "label": "Day Count Convention", "options": "30/360\nActual/360\nActual/365\nActual/Actual"},
            {"fieldname": "is_cash", "fieldtype": "Check", "label": "Is Cash"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "All", "read": 1}
        ]
    }

    # 3. Instrument Category
    instrument_category = {
        "name": "Instrument Category",
        "module": "Asset Management",
        "autoname": "field:code",
        "naming_rule": "By fieldname",
        "fields": [
            {"fieldname": "code", "fieldtype": "Data", "label": "Code", "reqd": 1, "unique": 1},
            {"fieldname": "category_name", "fieldtype": "Data", "label": "Category Name", "reqd": 1}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "All", "read": 1}
        ]
    }

    # 4. Instrument Type
    instrument_type = {
        "name": "Instrument Type",
        "module": "Asset Management",
        "autoname": "field:code",
        "naming_rule": "By fieldname",
        "fields": [
            {"fieldname": "code", "fieldtype": "Data", "label": "Code", "reqd": 1, "unique": 1},
            {"fieldname": "type_name", "fieldtype": "Data", "label": "Name", "reqd": 1},
            {"fieldname": "instrument_category", "fieldtype": "Link", "label": "Instrument Category", "options": "Instrument Category"},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "settlement_days", "fieldtype": "Int", "label": "Settlement Days (T+N)", "default": 3},
            {"fieldname": "decimal_places", "fieldtype": "Int", "label": "Decimal Places", "default": 4},
            {"fieldname": "settlement_model", "fieldtype": "Select", "label": "Settlement Model", "options": "\nGross\nNet"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "All", "read": 1}
        ]
    }

    # 5. Financial Instrument
    instrument = {
        "name": "Financial Instrument",
        "module": "Asset Management",
        "autoname": "field:code",
        "naming_rule": "By fieldname",
        "fields": [
            {"fieldname": "sec_main", "fieldtype": "Section Break", "label": "Basic Information"},
            {"fieldname": "code", "fieldtype": "Data", "label": "Code / Ticker", "reqd": 1, "unique": 1},
            {"fieldname": "instrument_name", "fieldtype": "Data", "label": "Instrument Name", "reqd": 1},
            {"fieldname": "isin_no", "fieldtype": "Data", "label": "ISIN No"},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "instrument_type", "fieldtype": "Link", "label": "Instrument Type", "options": "Instrument Type", "reqd": 1},
            {"fieldname": "instrument_category", "fieldtype": "Link", "label": "Instrument Category", "options": "Instrument Category"},
            {"fieldname": "asset_type", "fieldtype": "Link", "label": "Asset Type", "options": "Asset Type"},

            {"fieldname": "sec_dates_rates", "fieldtype": "Section Break", "label": "Dates & Yield"},
            {"fieldname": "coupon_rate", "fieldtype": "Percent", "label": "Coupon Rate %"},
            {"fieldname": "issue_date", "fieldtype": "Date", "label": "Issue Date"},
            {"fieldname": "maturity_date", "fieldtype": "Date", "label": "Maturity Date"},
            {"fieldname": "col_break_2", "fieldtype": "Column Break"},
            {"fieldname": "face_value", "fieldtype": "Currency", "label": "Face Value / Par Value"},
            {"fieldname": "unit_price", "fieldtype": "Currency", "label": "Latest Unit Price"},
            {"fieldname": "regulator_limit_pct", "fieldtype": "Percent", "label": "Regulator Limit %"},
            {"fieldname": "internal_limit_pct", "fieldtype": "Percent", "label": "Internal Limit %"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "All", "read": 1}
        ]
    }

    # 6. Instrument Price
    instrument_price = {
        "name": "Instrument Price",
        "module": "Asset Management",
        "autoname": "naming_series:",
        "naming_rule": "By \"Naming Series\" field",
        "fields": [
            {"fieldname": "naming_series", "fieldtype": "Select", "label": "Series", "options": "PRC-.YYYY.-.#####", "default": "PRC-.YYYY.-.#####"},
            {"fieldname": "instrument", "fieldtype": "Link", "label": "Instrument", "options": "Financial Instrument", "reqd": 1},
            {"fieldname": "value_date", "fieldtype": "Date", "label": "Value Date", "reqd": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "clean_price", "fieldtype": "Currency", "label": "Clean Price"},
            {"fieldname": "dirty_price", "fieldtype": "Currency", "label": "Dirty Price"},
            {"fieldname": "yield_pct", "fieldtype": "Percent", "label": "Yield %"},
            {"fieldname": "accrued_interest", "fieldtype": "Currency", "label": "Accrued Interest"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "All", "read": 1}
        ]
    }

    # 7. Investment Portfolio
    portfolio = {
        "name": "Investment Portfolio",
        "module": "Asset Management",
        "autoname": "field:portfolio_code",
        "naming_rule": "By fieldname",
        "fields": [
            {"fieldname": "sec_main", "fieldtype": "Section Break", "label": "Portfolio Details"},
            {"fieldname": "portfolio_code", "fieldtype": "Data", "label": "Portfolio Code", "reqd": 1, "unique": 1},
            {"fieldname": "portfolio_name", "fieldtype": "Data", "label": "Portfolio Name", "reqd": 1},
            {"fieldname": "portfolio_type", "fieldtype": "Select", "label": "Portfolio Type", "options": "\nUnit Trust\nPension Fund\nDiscretionary\nNon-Discretionary\nGratuity Fund", "reqd": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Active\nInactive\nClosed", "default": "Active"},
            {"fieldname": "inception_date", "fieldtype": "Date", "label": "Inception Date"},
            {"fieldname": "trading_currency", "fieldtype": "Link", "label": "Trading Currency", "options": "Currency"},
            {"fieldname": "portfolio_manager", "fieldtype": "Link", "label": "Portfolio Manager", "options": "User"},
            {"fieldname": "custodian", "fieldtype": "Data", "label": "Custodian Code / Name"},

            {"fieldname": "sec_risk", "fieldtype": "Section Break", "label": "Risk & Limits"},
            {"fieldname": "risk_profile", "fieldtype": "Select", "label": "Risk Profile", "options": "Conservative\nModerate\nAggressive\nVery Aggressive"},
            {"fieldname": "investment_horizon", "fieldtype": "Select", "label": "Investment Horizon", "options": "Short Term (<1yr)\nMedium Term (1-3yrs)\nLong Term (3-5yrs)\nVery Long Term (>5yrs)"},
            {"fieldname": "col_break_2", "fieldtype": "Column Break"},
            {"fieldname": "credit_limit", "fieldtype": "Currency", "label": "Credit Limit"},
            {"fieldname": "cscs_account_no", "fieldtype": "Data", "label": "CSCS Account No."}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "All", "read": 1}
        ]
    }

    # 8. Fund Fee Setup
    fund_fee = {
        "name": "Fund Fee Setup",
        "module": "Asset Management",
        "autoname": "naming_series:",
        "naming_rule": "By \"Naming Series\" field",
        "fields": [
            {"fieldname": "naming_series", "fieldtype": "Select", "label": "Series", "options": "FEE-.#####", "default": "FEE-.#####", "reqd": 1},
            {"fieldname": "portfolio", "fieldtype": "Link", "label": "Portfolio / Fund", "options": "Investment Portfolio", "reqd": 1},
            {"fieldname": "fee_type", "fieldtype": "Select", "label": "Fee Type", "options": "Management Fee\nCustodian Fee\nTrustee Fee\nAdvisory Fee\nIncentive / Performance Fee", "reqd": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "fee_percentage", "fieldtype": "Percent", "label": "Annual Fee %", "reqd": 1},
            {"fieldname": "vat_applicable", "fieldtype": "Check", "label": "VAT Applicable", "default": 1},
            {"fieldname": "active", "fieldtype": "Check", "label": "Active", "default": 1},
            {"fieldname": "sec_frequency", "fieldtype": "Section Break", "label": "Calculation Schedule"},
            {"fieldname": "frequency", "fieldtype": "Select", "label": "Accrual Frequency", "options": "Daily\nMonthly\nQuarterly\nAnnually", "default": "Daily"},
            {"fieldname": "col_break_2", "fieldtype": "Column Break"},
            {"fieldname": "effective_start_date", "fieldtype": "Date", "label": "Effective Start Date", "default": "Today", "reqd": 1},
            {"fieldname": "effective_end_date", "fieldtype": "Date", "label": "Effective End Date"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "All", "read": 1}
        ]
    }

    # 9. Asset Investor (Asset Management Client Master)
    asset_investor = {
        "name": "Asset Investor",
        "module": "Asset Management",
        "autoname": "field:investor_id",
        "naming_rule": "By fieldname",
        "fields": [
            {"fieldname": "sec_info", "fieldtype": "Section Break", "label": "Investor Information"},
            {"fieldname": "investor_id", "fieldtype": "Data", "label": "Investor ID / Account No", "reqd": 1, "unique": 1},
            {"fieldname": "investor_name", "fieldtype": "Data", "label": "Investor Name", "reqd": 1},
            {"fieldname": "investor_type", "fieldtype": "Select", "label": "Investor Type", "options": "Individual\nInstitutional\nHigh Net Worth\nTrust", "default": "Individual"},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "email", "fieldtype": "Data", "label": "Email Address", "options": "Email"},
            {"fieldname": "phone", "fieldtype": "Data", "label": "Phone Number"},
            {"fieldname": "tax_id", "fieldtype": "Data", "label": "Tax ID / TIN"},
            {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Active\nInactive\nSuspended", "default": "Active"},

            {"fieldname": "sec_kyc", "fieldtype": "Section Break", "label": "Investor KYC & Compliance"},
            {"fieldname": "kyc_status", "fieldtype": "Select", "label": "KYC Status", "options": "Pending\nVerified\nRejected", "default": "Pending"},
            {"fieldname": "pep_status", "fieldtype": "Select", "label": "PEP Status", "options": "No\nYes\nAssociated", "default": "No"},
            {"fieldname": "col_break_2", "fieldtype": "Column Break"},
            {"fieldname": "risk_tier", "fieldtype": "Select", "label": "Risk Tier", "options": "Low\nMedium\nHigh", "default": "Low"},
            {"fieldname": "verified_date", "fieldtype": "Date", "label": "KYC Verified Date", "read_only": 1}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "All", "read": 1}
        ]
    }

    # 10. Asset Investor KYC Document (Dedicated KYC for Asset Management)
    asset_kyc_doc = {
        "name": "Asset Investor KYC Document",
        "module": "Asset Management",
        "autoname": "naming_series:",
        "naming_rule": "By \"Naming Series\" field",
        "fields": [
            {"fieldname": "naming_series", "fieldtype": "Select", "label": "Series", "options": "AI-KYC-.YYYY.-.#####", "default": "AI-KYC-.YYYY.-.#####", "reqd": 1},
            {"fieldname": "investor", "fieldtype": "Link", "label": "Investor", "options": "Asset Investor", "reqd": 1},
            {"fieldname": "document_type", "fieldtype": "Select", "label": "Document Type", "options": "ID Card / Passport\nProof of Address\nCertificate of Incorporation\nBoard Resolution\nTax Certificate", "reqd": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "verification_status", "fieldtype": "Select", "label": "Status", "options": "Pending\nVerified\nRejected\nExpired", "default": "Pending"},
            {"fieldname": "expiry_date", "fieldtype": "Date", "label": "Expiry Date"},
            {"fieldname": "attachment", "fieldtype": "Attach", "label": "Uploaded File", "reqd": 1},
            {"fieldname": "col_break_2", "fieldtype": "Column Break"},
            {"fieldname": "verified_by", "fieldtype": "Link", "label": "Verified By", "options": "User", "read_only": 1},
            {"fieldname": "verification_date", "fieldtype": "Date", "label": "Verification Date", "read_only": 1}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "All", "read": 1}
        ]
    }

    for dt in [
        investment_setup,
        asset_type,
        instrument_category,
        instrument_type,
        instrument,
        instrument_price,
        portfolio,
        fund_fee,
        asset_investor,
        asset_kyc_doc
    ]:
        make_doctype(dt)

    frappe.db.commit()
    print("Clean Asset Management DocTypes created successfully!")

