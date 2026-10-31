import frappe

def seed_data():
    # 1. Seed Asset Types from BC
    asset_types = [
        {"code": "EQTY", "description": "Equities / Quoted Shares", "general_type": "Equity", "stock_market_class": "Capital Markets", "day_count_convention": "Actual/365", "is_cash": 0},
        {"code": "BOND", "description": "Treasury & Corporate Bonds", "general_type": "Bond", "stock_market_class": "Bonds", "day_count_convention": "30/360", "is_cash": 0},
        {"code": "TBILL", "description": "Treasury Bills", "general_type": "Treasury Bills", "stock_market_class": "Treasury Bills", "day_count_convention": "Actual/360", "is_cash": 0},
        {"code": "MM", "description": "Money Market Instruments", "general_type": "Money Market", "stock_market_class": "Money Markets", "day_count_convention": "Actual/365", "is_cash": 0},
        {"code": "CASH", "description": "Cash & Call Balances", "general_type": "Money Market", "stock_market_class": "Money Markets", "day_count_convention": "Actual/365", "is_cash": 1},
        {"code": "REITS", "description": "Real Estate Investment Trusts", "general_type": "REITS", "stock_market_class": "Real Estate", "day_count_convention": "Actual/365", "is_cash": 0}
    ]
    for at in asset_types:
        if not frappe.db.exists("Asset Type", at["code"]):
            doc = frappe.new_doc("Asset Type")
            doc.update(at)
            doc.insert(ignore_permissions=True)
            print(f"Seeded Asset Type: {at['code']}")

    # 2. Seed Instrument Categories
    inst_cats = [
        {"code": "GOVT_DEBT", "category_name": "Government Sovereign Debt"},
        {"code": "CORP_DEBT", "category_name": "Corporate Debt Securities"},
        {"code": "DOMESTIC_EQ", "category_name": "Domestic Listed Equities"},
        {"code": "FOREIGN_EQ", "category_name": "Foreign Listed Equities"}
    ]
    for ic in inst_cats:
        if not frappe.db.exists("Instrument Category", ic["code"]):
            doc = frappe.new_doc("Instrument Category")
            doc.update(ic)
            doc.insert(ignore_permissions=True)
            print(f"Seeded Instrument Category: {ic['code']}")

    # 3. Seed Instrument Types
    inst_types = [
        {"code": "EQ-ORD", "type_name": "Ordinary Shares", "instrument_category": "DOMESTIC_EQ", "settlement_days": 3, "decimal_places": 2, "settlement_model": "Net"},
        {"code": "T-BOND", "type_name": "Treasury Bond", "instrument_category": "GOVT_DEBT", "settlement_days": 2, "decimal_places": 4, "settlement_model": "Gross"},
        {"code": "TBILL", "type_name": "Treasury Bill", "instrument_category": "GOVT_DEBT", "settlement_days": 2, "decimal_places": 4, "settlement_model": "Gross"}
    ]
    for it in inst_types:
        if not frappe.db.exists("Instrument Type", it["code"]):
            doc = frappe.new_doc("Instrument Type")
            doc.update(it)
            doc.insert(ignore_permissions=True)
            print(f"Seeded Instrument Type: {it['code']}")

    # 4. Seed Investment Setup Defaults
    setup = frappe.get_single("Investment Setup")
    setup.withholding_tax_percentage = 10.0
    setup.vat_percent = 7.5
    setup.sec_percent = 0.3
    setup.nse_percent = 0.3
    setup.cscs_fixed_amount = 54.0
    setup.stamp_percent = 0.075
    setup.save(ignore_permissions=True)
    print("Seeded Investment Setup defaults.")

    # 5. Seed Brokerage Required Documents (KYC Master Checklist)
    kyc_docs = [
        {"document_code": "NAT_ID", "document_name": "National Identity Card / International Passport", "applies_to": "Both", "is_mandatory": 1, "validity_period_months": 24},
        {"document_code": "PROOF_ADDR", "document_name": "Utility Bill / Proof of Residential Address", "applies_to": "Both", "is_mandatory": 1, "validity_period_months": 6},
        {"document_code": "CAC_CERT", "document_name": "Certificate of Incorporation / Registration", "applies_to": "Corporate", "is_mandatory": 1, "validity_period_months": 0},
        {"document_code": "BOARD_RES", "document_name": "Board Resolution & Signing Mandate", "applies_to": "Corporate", "is_mandatory": 1, "validity_period_months": 0},
        {"document_code": "TIN_CERT", "document_name": "Tax Identification Certificate", "applies_to": "Both", "is_mandatory": 1, "validity_period_months": 0}
    ]
    for kd in kyc_docs:
        if not frappe.db.exists("Brokerage Required Document", kd["document_code"]):
            doc = frappe.new_doc("Brokerage Required Document")
            doc.update(kd)
            doc.insert(ignore_permissions=True)
            print(f"Seeded Brokerage Required Document: {kd['document_code']}")

    frappe.db.commit()
    print("Master fixtures and BC baseline data successfully seeded!")

