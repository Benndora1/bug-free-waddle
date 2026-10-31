import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ROLES = [
    {"role_name": "Asset Management Operations", "desk_access": 1},
    {"role_name": "Asset Investment Manager", "desk_access": 1},
    {"role_name": "Asset Fund Administrator", "desk_access": 1},
    {"role_name": "Asset Finance Officer", "desk_access": 1},
    {"role_name": "Asset Compliance Officer", "desk_access": 1},
    {"role_name": "Asset Client Service", "desk_access": 1},
    {"role_name": "Asset Agent", "desk_access": 1},
    {"role_name": "Asset Investor Portal User", "desk_access": 0},
    {"role_name": "Asset Management Admin", "desk_access": 1},
]

def make_roles():
    print("=== CREATING ASSET MANAGEMENT ROLES ===")
    for r in ROLES:
        role_name = r["role_name"]
        if not frappe.db.exists("Role", role_name):
            doc = frappe.new_doc("Role")
            doc.role_name = role_name
            doc.desk_access = r["desk_access"]
            doc.insert(ignore_permissions=True)
            print(f"Created Role: {role_name}")
        else:
            print(f"Role {role_name} already exists.")

def make_doctype(data):
    name = data.get("name")
    if frappe.db.exists("DocType", name):
        doc = frappe.get_doc("DocType", name)
        doc.update(data)
        doc.custom = 0
        doc.save(ignore_permissions=True)
        print(f"Updated DocType: '{name}'")
    else:
        doc = frappe.new_doc("DocType")
        doc.update(data)
        doc.custom = 0
        doc.insert(ignore_permissions=True)
        print(f"Created DocType: '{name}'")

def setup_sprint1_doctypes():
    print("\n=== CREATING SPRINT 1 DOCTYPES ===")

    # 1. Joint Holder / Signatory (Child Table)
    joint_signatory_dt = {
        "name": "Asset Investor Signatory",
        "module": "Asset Management",
        "istable": 1,
        "fields": [
            {"fieldname": "full_name", "fieldtype": "Data", "label": "Full Name", "reqd": 1, "in_list_view": 1},
            {"fieldname": "signatory_type", "fieldtype": "Select", "label": "Type", "options": "Joint Holder\nDirector\nTrustee\nAuthorized Signatory", "default": "Joint Holder", "in_list_view": 1},
            {"fieldname": "identification_type", "fieldtype": "Select", "label": "ID Type", "options": "National ID\nPassport\nAlien ID", "default": "National ID"},
            {"fieldname": "identification_no", "fieldtype": "Data", "label": "ID Number", "in_list_view": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "phone", "fieldtype": "Data", "label": "Phone Number", "in_list_view": 1},
            {"fieldname": "email", "fieldtype": "Data", "label": "Email Address"},
            {"fieldname": "pep_status", "fieldtype": "Select", "label": "PEP Status", "options": "No\nYes\nAssociated", "default": "No"},
            {"fieldname": "signature", "fieldtype": "Attach", "label": "Specimen Signature"}
        ]
    }

    # 2. Next of Kin / Beneficiary (Child Table)
    beneficiary_dt = {
        "name": "Asset Investor Beneficiary",
        "module": "Asset Management",
        "istable": 1,
        "fields": [
            {"fieldname": "full_name", "fieldtype": "Data", "label": "Beneficiary Name", "reqd": 1, "in_list_view": 1},
            {"fieldname": "relationship", "fieldtype": "Select", "label": "Relationship", "options": "Spouse\nChild\nParent\nSibling\nTrustee\nOther", "default": "Spouse", "in_list_view": 1},
            {"fieldname": "allocation_percent", "fieldtype": "Percent", "label": "Allocation %", "reqd": 1, "in_list_view": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "phone", "fieldtype": "Data", "label": "Phone Number", "in_list_view": 1},
            {"fieldname": "email", "fieldtype": "Data", "label": "Email Address"},
            {"fieldname": "identification_no", "fieldtype": "Data", "label": "National ID / Passport"}
        ]
    }

    # 3. Required Document Master
    required_doc_dt = {
        "name": "Asset Required Document",
        "module": "Asset Management",
        "autoname": "field:document_code",
        "naming_rule": "By fieldname",
        "fields": [
            {"fieldname": "document_code", "fieldtype": "Data", "label": "Document Code", "reqd": 1, "unique": 1},
            {"fieldname": "document_name", "fieldtype": "Data", "label": "Document Name", "reqd": 1, "in_list_view": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "mandatory", "fieldtype": "Check", "label": "Mandatory", "default": 1, "in_list_view": 1},
            {"fieldname": "investor_type", "fieldtype": "Select", "label": "Investor Type", "options": "All\nIndividual\nJoint\nCorporate\nTrust / Institutional", "default": "All", "in_list_view": 1},
            {"fieldname": "description", "fieldtype": "Small Text", "label": "Description / Guidelines"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Management Admin", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Compliance Officer", "read": 1, "write": 1},
            {"role": "Asset Management Operations", "read": 1}
        ]
    }

    # 4. Investor KYC Document Line (Child or Attached)
    investor_kyc_dt = {
        "name": "Asset Investor KYC Document",
        "module": "Asset Management",
        "autoname": "naming_series:",
        "naming_rule": "By \"Naming Series\" field",
        "fields": [
            {"fieldname": "naming_series", "fieldtype": "Select", "label": "Series", "options": "AI-KYC-.YYYY.-.#####", "default": "AI-KYC-.YYYY.-.#####", "reqd": 1},
            {"fieldname": "document_code", "fieldtype": "Link", "label": "Required Document", "options": "Asset Required Document", "reqd": 1, "in_list_view": 1},
            {"fieldname": "document_name", "fieldtype": "Data", "label": "Document Name", "in_list_view": 1},
            {"fieldname": "parent_application", "fieldtype": "Link", "label": "Application Ref", "options": "Asset Investor Application"},
            {"fieldname": "investor", "fieldtype": "Link", "label": "Investor", "options": "Asset Investor", "in_list_view": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "verification_status", "fieldtype": "Select", "label": "Status", "options": "Pending\nVerified\nRejected\nExpired", "default": "Pending", "in_list_view": 1},
            {"fieldname": "expiry_date", "fieldtype": "Date", "label": "Expiry Date"},
            {"fieldname": "attachment", "fieldtype": "Attach", "label": "Uploaded File", "in_list_view": 1},
            {"fieldname": "col_break_2", "fieldtype": "Column Break"},
            {"fieldname": "verified_by", "fieldtype": "Link", "label": "Verified By", "options": "User", "read_only": 1},
            {"fieldname": "verification_date", "fieldtype": "Date", "label": "Verification Date", "read_only": 1},
            {"fieldname": "verification_notes", "fieldtype": "Small Text", "label": "Verification Notes"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Management Admin", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Compliance Officer", "read": 1, "write": 1, "create": 1},
            {"role": "Asset Management Operations", "read": 1, "write": 1, "create": 1}
        ]
    }

    # 5. Asset Investor Application (Account Opening Workflow)
    investor_app_dt = {
        "name": "Asset Investor Application",
        "module": "Asset Management",
        "autoname": "naming_series:",
        "naming_rule": "By \"Naming Series\" field",
        "is_submittable": 1,
        "track_changes": 1,
        "fields": [
            {"fieldname": "naming_series", "fieldtype": "Select", "label": "Series", "options": "APP-.YYYY.-.#####", "default": "APP-.YYYY.-.#####", "reqd": 1},
            {"fieldname": "application_date", "fieldtype": "Date", "label": "Application Date", "default": "Today", "reqd": 1, "in_list_view": 1},
            {"fieldname": "onboarding_channel", "fieldtype": "Select", "label": "Onboarding Channel", "options": "Face to Face\nAgent\nOnline Portal\nWholesale / Direct", "default": "Face to Face", "in_list_view": 1},
            {"fieldname": "agent", "fieldtype": "Data", "label": "Agent Code / Name"},
            {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Draft\nPending Approval\nApproved\nRejected", "default": "Draft", "in_list_view": 1, "read_only": 1},

            {"fieldname": "sec_investor_details", "fieldtype": "Section Break", "label": "Investor Identity & Categorization"},
            {"fieldname": "investor_type", "fieldtype": "Select", "label": "Investor Type", "options": "Individual\nJoint\nCorporate\nTrust / Institutional", "default": "Individual", "reqd": 1, "in_list_view": 1},
            {"fieldname": "client_category", "fieldtype": "Select", "label": "Client Category", "options": "Retail\nHigh Net Worth\nInstitutional\nPension Fund", "default": "Retail", "reqd": 1},
            {"fieldname": "investor_name", "fieldtype": "Data", "label": "Investor / Entity Name", "reqd": 1, "in_list_view": 1},
            {"fieldname": "col_break_id", "fieldtype": "Column Break"},
            {"fieldname": "identification_type", "fieldtype": "Select", "label": "ID Type", "options": "National ID\nPassport\nAlien ID\nCertificate of Incorporation\nTrust Deed", "default": "National ID", "reqd": 1},
            {"fieldname": "identification_no", "fieldtype": "Data", "label": "ID / Registration Number", "reqd": 1},
            {"fieldname": "tax_id", "fieldtype": "Data", "label": "Tax ID / TIN", "reqd": 1},
            {"fieldname": "country_of_residence", "fieldtype": "Link", "label": "Country of Residence", "options": "Country", "default": "Uganda"},

            {"fieldname": "sec_contact", "fieldtype": "Section Break", "label": "Contact & Address"},
            {"fieldname": "email", "fieldtype": "Data", "label": "Email Address", "options": "Email", "reqd": 1},
            {"fieldname": "phone", "fieldtype": "Data", "label": "Phone Number", "reqd": 1},
            {"fieldname": "col_break_addr", "fieldtype": "Column Break"},
            {"fieldname": "physical_address", "fieldtype": "Small Text", "label": "Physical Address", "reqd": 1},
            {"fieldname": "postal_address", "fieldtype": "Data", "label": "Postal Address"},
            {"fieldname": "city", "fieldtype": "Data", "label": "City", "default": "Kampala"},

            {"fieldname": "sec_bank", "fieldtype": "Section Break", "label": "Settlement Bank Account (For Redemptions)"},
            {"fieldname": "bank_name", "fieldtype": "Data", "label": "Bank Name", "default": "Stanbic Bank Uganda", "reqd": 1},
            {"fieldname": "bank_branch", "fieldtype": "Data", "label": "Branch Name", "default": "Crested Towers", "reqd": 1},
            {"fieldname": "col_break_bnk", "fieldtype": "Column Break"},
            {"fieldname": "bank_account_name", "fieldtype": "Data", "label": "Account Name", "reqd": 1},
            {"fieldname": "bank_account_no", "fieldtype": "Data", "label": "Account Number", "reqd": 1},
            {"fieldname": "settlement_currency", "fieldtype": "Link", "label": "Settlement Currency", "options": "Currency", "default": "UGX"},

            {"fieldname": "sec_signatories", "fieldtype": "Section Break", "label": "Joint Holders & Mandated Signatories"},
            {"fieldname": "signatories", "fieldtype": "Table", "label": "Signatories", "options": "Asset Investor Signatory"},

            {"fieldname": "sec_beneficiaries", "fieldtype": "Section Break", "label": "Next of Kin & Beneficiaries"},
            {"fieldname": "beneficiaries", "fieldtype": "Table", "label": "Beneficiaries", "options": "Asset Investor Beneficiary"},

            {"fieldname": "sec_compliance", "fieldtype": "Section Break", "label": "PEP, Sanctions & Risk Scoring"},
            {"fieldname": "pep_status", "fieldtype": "Select", "label": "PEP Status", "options": "No\nYes\nAssociated", "default": "No"},
            {"fieldname": "sanction_status", "fieldtype": "Select", "label": "Sanctions Match", "options": "No\nYes", "default": "No"},
            {"fieldname": "edd_required", "fieldtype": "Check", "label": "Enhanced Due Diligence (EDD) Required", "read_only": 1},
            {"fieldname": "col_break_risk", "fieldtype": "Column Break"},
            {"fieldname": "risk_score", "fieldtype": "Float", "label": "Risk Score", "read_only": 1},
            {"fieldname": "risk_tier", "fieldtype": "Select", "label": "Risk Tier", "options": "Low\nMedium\nHigh", "default": "Low", "read_only": 1},
            {"fieldname": "edd_notes", "fieldtype": "Small Text", "label": "EDD & Compliance Findings"},

            {"fieldname": "sec_approval", "fieldtype": "Section Break", "label": "Approval & Account Creation"},
            {"fieldname": "reviewed_by", "fieldtype": "Link", "label": "Reviewed / Verified By", "options": "User", "read_only": 1},
            {"fieldname": "approved_by_ce", "fieldtype": "Check", "label": "Chief Executive (CE) Approval (Required for PEP/High-Risk)"},
            {"fieldname": "approval_date", "fieldtype": "Date", "label": "Approval Date", "read_only": 1},
            {"fieldname": "created_investor_account", "fieldtype": "Link", "label": "Created Investor Account", "options": "Asset Investor", "read_only": 1},
            {"fieldname": "col_break_appr", "fieldtype": "Column Break"},
            {"fieldname": "rejection_reason", "fieldtype": "Small Text", "label": "Rejection Reason"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 1, "cancel": 1, "amend": 1},
            {"role": "Asset Management Admin", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 1, "cancel": 1, "amend": 1},
            {"role": "Asset Compliance Officer", "read": 1, "write": 1, "submit": 1},
            {"role": "Asset Management Operations", "read": 1, "write": 1, "create": 1, "submit": 1}
        ]
    }

    # 6. Asset Investor (Updated Master)
    investor_master_dt = {
        "name": "Asset Investor",
        "module": "Asset Management",
        "autoname": "field:investor_id",
        "naming_rule": "By fieldname",
        "track_changes": 1,
        "fields": [
            {"fieldname": "sec_info", "fieldtype": "Section Break", "label": "Investor Account Information"},
            {"fieldname": "investor_id", "fieldtype": "Data", "label": "Investor ID / Account No", "reqd": 1, "unique": 1, "in_list_view": 1},
            {"fieldname": "investor_name", "fieldtype": "Data", "label": "Investor Name", "reqd": 1, "in_list_view": 1},
            {"fieldname": "investor_type", "fieldtype": "Select", "label": "Investor Type", "options": "Individual\nJoint\nCorporate\nTrust / Institutional", "default": "Individual", "in_list_view": 1},
            {"fieldname": "client_category", "fieldtype": "Select", "label": "Client Category", "options": "Retail\nHigh Net Worth\nInstitutional\nPension Fund", "default": "Retail"},
            {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Active\nDormant\nSuspended\nClosed", "default": "Active", "in_list_view": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "email", "fieldtype": "Data", "label": "Email Address", "options": "Email"},
            {"fieldname": "phone", "fieldtype": "Data", "label": "Phone Number"},
            {"fieldname": "tax_id", "fieldtype": "Data", "label": "Tax ID / TIN"},
            {"fieldname": "country_of_residence", "fieldtype": "Link", "label": "Country of Residence", "options": "Country", "default": "Uganda"},
            {"fieldname": "created_from_application", "fieldtype": "Link", "label": "Originated Application", "options": "Asset Investor Application", "read_only": 1},

            {"fieldname": "sec_bank", "fieldtype": "Section Break", "label": "Settlement Bank Account"},
            {"fieldname": "bank_name", "fieldtype": "Data", "label": "Bank Name"},
            {"fieldname": "bank_branch", "fieldtype": "Data", "label": "Branch Name"},
            {"fieldname": "col_break_bnk", "fieldtype": "Column Break"},
            {"fieldname": "bank_account_name", "fieldtype": "Data", "label": "Account Name"},
            {"fieldname": "bank_account_no", "fieldtype": "Data", "label": "Account Number"},
            {"fieldname": "settlement_currency", "fieldtype": "Link", "label": "Currency", "options": "Currency", "default": "UGX"},

            {"fieldname": "sec_kyc", "fieldtype": "Section Break", "label": "Investor KYC & Compliance Status"},
            {"fieldname": "kyc_status", "fieldtype": "Select", "label": "KYC Status", "options": "Pending\nVerified\nRejected", "default": "Verified"},
            {"fieldname": "pep_status", "fieldtype": "Select", "label": "PEP Status", "options": "No\nYes\nAssociated", "default": "No"},
            {"fieldname": "sanction_status", "fieldtype": "Select", "label": "Sanctions Match", "options": "No\nYes", "default": "No"},
            {"fieldname": "col_break_2", "fieldtype": "Column Break"},
            {"fieldname": "risk_tier", "fieldtype": "Select", "label": "Risk Tier", "options": "Low\nMedium\nHigh", "default": "Low", "in_list_view": 1},
            {"fieldname": "verified_date", "fieldtype": "Date", "label": "KYC Verified Date", "read_only": 1},
            {"fieldname": "last_review_date", "fieldtype": "Date", "label": "Last Review Date"},
            {"fieldname": "next_review_date", "fieldtype": "Date", "label": "Next Periodic Review Date"},

            {"fieldname": "sec_portfolio_summary", "fieldtype": "Section Break", "label": "Portfolio Holdings Summary"},
            {"fieldname": "total_portfolio_value", "fieldtype": "Currency", "label": "Total Portfolio Net Value", "read_only": 1},
            {"fieldname": "col_break_pf", "fieldtype": "Column Break"},
            {"fieldname": "total_units_held", "fieldtype": "Float", "label": "Total Units Held Across Funds", "read_only": 1}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Management Admin", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Compliance Officer", "read": 1, "write": 1},
            {"role": "Asset Fund Administrator", "read": 1, "write": 1},
            {"role": "Asset Management Operations", "read": 1, "write": 1, "create": 1},
            {"role": "Asset Client Service", "read": 1}
        ]
    }

    # 7. Risk Profile Setup Master
    risk_profile_dt = {
        "name": "Asset Risk Profile",
        "module": "Asset Management",
        "autoname": "field:code",
        "naming_rule": "By fieldname",
        "fields": [
            {"fieldname": "code", "fieldtype": "Data", "label": "Risk Code", "reqd": 1, "unique": 1},
            {"fieldname": "risk_tier", "fieldtype": "Select", "label": "Risk Tier", "options": "Low\nMedium\nHigh", "default": "Low", "in_list_view": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "lower_score", "fieldtype": "Float", "label": "Lower Score Threshold", "reqd": 1, "in_list_view": 1},
            {"fieldname": "upper_score", "fieldtype": "Float", "label": "Upper Score Threshold", "reqd": 1, "in_list_view": 1},
            {"fieldname": "review_frequency_months", "fieldtype": "Int", "label": "Periodic Review (Months)", "default": 12},
            {"fieldname": "description", "fieldtype": "Small Text", "label": "Description & Action Required"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Management Admin", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Compliance Officer", "read": 1, "write": 1}
        ]
    }

    # 8. PEP & Sanction Setup Master
    pep_sanction_dt = {
        "name": "Asset PEP Sanction Setup",
        "module": "Asset Management",
        "autoname": "field:rule_code",
        "naming_rule": "By fieldname",
        "fields": [
            {"fieldname": "rule_code", "fieldtype": "Data", "label": "Rule Code", "reqd": 1, "unique": 1},
            {"fieldname": "risk_type", "fieldtype": "Select", "label": "Risk Type", "options": "PEP\nSANCTION", "reqd": 1, "in_list_view": 1},
            {"fieldname": "is_match", "fieldtype": "Check", "label": "Is Match", "default": 1, "in_list_view": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "risk_score_impact", "fieldtype": "Float", "label": "Score Impact", "default": 50, "in_list_view": 1},
            {"fieldname": "requires_ce_approval", "fieldtype": "Check", "label": "Requires Chief Executive (CE) Approval", "default": 1},
            {"fieldname": "description", "fieldtype": "Small Text", "label": "Rule Description"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Management Admin", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Compliance Officer", "read": 1, "write": 1}
        ]
    }

    # 9. Suspicious Transaction Rule
    suspicious_rule_dt = {
        "name": "Asset Suspicious Transaction Rule",
        "module": "Asset Management",
        "autoname": "field:rule_id",
        "naming_rule": "By fieldname",
        "fields": [
            {"fieldname": "rule_id", "fieldtype": "Data", "label": "Rule ID", "reqd": 1, "unique": 1},
            {"fieldname": "rule_name", "fieldtype": "Data", "label": "Rule Name", "reqd": 1, "in_list_view": 1},
            {"fieldname": "rule_type", "fieldtype": "Select", "label": "Rule Type", "options": "Large Cash Transaction\nHigh Velocity Deposits\nRapid Full Redemption\nStructuring / Smurfing", "default": "Large Cash Transaction", "in_list_view": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "threshold_amount", "fieldtype": "Currency", "label": "Threshold Amount (UGX)", "default": 20000000, "in_list_view": 1},
            {"fieldname": "threshold_days", "fieldtype": "Int", "label": "Window (Days)", "default": 1},
            {"fieldname": "active", "fieldtype": "Check", "label": "Active", "default": 1, "in_list_view": 1},
            {"fieldname": "description", "fieldtype": "Small Text", "label": "Description"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Management Admin", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Compliance Officer", "read": 1, "write": 1}
        ]
    }

    # 10. Suspicious Transaction Log
    suspicious_log_dt = {
        "name": "Asset Suspicious Transaction Log",
        "module": "Asset Management",
        "autoname": "naming_series:",
        "naming_rule": "By \"Naming Series\" field",
        "track_changes": 1,
        "fields": [
            {"fieldname": "naming_series", "fieldtype": "Select", "label": "Series", "options": "AML-LOG-.YYYY.-.#####", "default": "AML-LOG-.YYYY.-.#####", "reqd": 1},
            {"fieldname": "log_date", "fieldtype": "Date", "label": "Log Date", "default": "Today", "reqd": 1, "in_list_view": 1},
            {"fieldname": "rule", "fieldtype": "Link", "label": "Triggered Rule", "options": "Asset Suspicious Transaction Rule", "reqd": 1, "in_list_view": 1},
            {"fieldname": "investor", "fieldtype": "Link", "label": "Investor", "options": "Asset Investor", "reqd": 1, "in_list_view": 1},
            {"fieldname": "transaction_reference", "fieldtype": "Data", "label": "Transaction Ref", "in_list_view": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "amount", "fieldtype": "Currency", "label": "Transaction Amount", "in_list_view": 1},
            {"fieldname": "status", "fieldtype": "Select", "label": "Compliance Status", "options": "Open\nInvestigating\nEscalated to CE\nCleared\nReported to FIA", "default": "Open", "in_list_view": 1},
            {"fieldname": "action_taken", "fieldtype": "Select", "label": "Action Taken", "options": "None\nAccount Lien Applied\nSAR Filed\nCleared without SAR", "default": "None"},
            {"fieldname": "col_break_2", "fieldtype": "Column Break"},
            {"fieldname": "reviewed_by", "fieldtype": "Link", "label": "Reviewed By", "options": "User"},
            {"fieldname": "review_date", "fieldtype": "Date", "label": "Review Date"},
            {"fieldname": "investigation_notes", "fieldtype": "Small Text", "label": "Investigation Findings"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Management Admin", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Compliance Officer", "read": 1, "write": 1, "create": 1}
        ]
    }

    # 11. CRM SLA Setup Master
    crm_sla_dt = {
        "name": "Asset CRM SLA Setup",
        "module": "Asset Management",
        "autoname": "field:code",
        "naming_rule": "By fieldname",
        "fields": [
            {"fieldname": "code", "fieldtype": "Data", "label": "SLA Code", "reqd": 1, "unique": 1},
            {"fieldname": "category", "fieldtype": "Select", "label": "Interaction Category", "options": "General Inquiry\nAccount Statement Request\nSubscription Follow-up\nRedemption Follow-up\nFund Switch Request\nBank Account Update\nClient Complaint\nTax Certificate Request", "reqd": 1, "in_list_view": 1},
            {"fieldname": "functional_group", "fieldtype": "Select", "label": "Functional Group", "options": "Operations\nFund Accounting\nInvestment Desk\nCompliance\nClient Service\nFinance", "default": "Client Service", "in_list_view": 1},
            {"fieldname": "col_break_1", "fieldtype": "Column Break"},
            {"fieldname": "internal_sla_hours", "fieldtype": "Int", "label": "Internal SLA (Hours)", "default": 4, "reqd": 1, "in_list_view": 1},
            {"fieldname": "external_sla_hours", "fieldtype": "Int", "label": "External SLA (Hours)", "default": 24, "reqd": 1, "in_list_view": 1},
            {"fieldname": "active", "fieldtype": "Check", "label": "Active", "default": 1, "in_list_view": 1},
            {"fieldname": "description", "fieldtype": "Small Text", "label": "Description & Resolution Standard"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Management Admin", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Client Service", "read": 1, "write": 1}
        ]
    }

    # 12. Client Interaction Header (Case / Ticket)
    interaction_dt = {
        "name": "Asset Client Interaction",
        "module": "Asset Management",
        "autoname": "naming_series:",
        "naming_rule": "By \"Naming Series\" field",
        "track_changes": 1,
        "fields": [
            {"fieldname": "naming_series", "fieldtype": "Select", "label": "Series", "options": "CASE-.YYYY.-.#####", "default": "CASE-.YYYY.-.#####", "reqd": 1},
            {"fieldname": "date_opened", "fieldtype": "Datetime", "label": "Date and Time Opened", "default": "Now", "reqd": 1, "in_list_view": 1},
            {"fieldname": "investor", "fieldtype": "Link", "label": "Investor Account", "options": "Asset Investor", "reqd": 1, "in_list_view": 1},
            {"fieldname": "investor_name", "fieldtype": "Data", "label": "Investor Name", "read_only": 1, "in_list_view": 1},
            {"fieldname": "channel", "fieldtype": "Select", "label": "Interaction Channel", "options": "Walk-in\nPhone Call\nEmail\nOnline Portal\nLetter / Physical", "default": "Walk-in", "in_list_view": 1},
            {"fieldname": "col_break_sla", "fieldtype": "Column Break"},
            {"fieldname": "sla_setup", "fieldtype": "Link", "label": "SLA Category", "options": "Asset CRM SLA Setup", "reqd": 1, "in_list_view": 1},
            {"fieldname": "status", "fieldtype": "Select", "label": "Status", "options": "Open\nIn Progress\nEscalated\nResolved\nClosed", "default": "Open", "in_list_view": 1},
            {"fieldname": "priority", "fieldtype": "Select", "label": "Priority", "options": "Low\nMedium\nHigh\nUrgent", "default": "Medium"},
            {"fieldname": "assigned_to", "fieldtype": "Link", "label": "Assigned Staff", "options": "User", "default": "Administrator"},

            {"fieldname": "sec_details", "fieldtype": "Section Break", "label": "Interaction Subject & Description"},
            {"fieldname": "subject", "fieldtype": "Data", "label": "Subject / Summary", "reqd": 1},
            {"fieldname": "description", "fieldtype": "Text", "label": "Detailed Client Inquiries / Request", "reqd": 1},

            {"fieldname": "sec_sla_tracking", "fieldtype": "Section Break", "label": "SLA Deadlines & Escalation"},
            {"fieldname": "target_due_datetime", "fieldtype": "Datetime", "label": "Target Due Date / Time", "read_only": 1},
            {"fieldname": "is_overdue", "fieldtype": "Check", "label": "Is Overdue", "read_only": 1},
            {"fieldname": "col_break_esc", "fieldtype": "Column Break"},
            {"fieldname": "escalation_level", "fieldtype": "Select", "label": "Escalation Level", "options": "Level 1 (Staff)\nLevel 2 (Team Leader)\nLevel 3 (Head of CX / CE)", "default": "Level 1 (Staff)"},
            {"fieldname": "escalated_to", "fieldtype": "Link", "label": "Escalated User", "options": "User"},

            {"fieldname": "sec_resolution", "fieldtype": "Section Break", "label": "Resolution & Feedback"},
            {"fieldname": "resolution_datetime", "fieldtype": "Datetime", "label": "Resolution Date and Time", "read_only": 1},
            {"fieldname": "resolved_by", "fieldtype": "Link", "label": "Resolved By", "options": "User", "read_only": 1},
            {"fieldname": "resolution_summary", "fieldtype": "Small Text", "label": "Resolution Action Taken"},
            {"fieldname": "col_break_fb", "fieldtype": "Column Break"},
            {"fieldname": "client_feedback", "fieldtype": "Select", "label": "Client Feedback", "options": "Pending\nSatisfied\nDissatisfied\nNeutral", "default": "Pending"},
            {"fieldname": "feedback_comments", "fieldtype": "Small Text", "label": "Client Feedback Comments"}
        ],
        "permissions": [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Management Admin", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Asset Client Service", "read": 1, "write": 1, "create": 1},
            {"role": "Asset Management Operations", "read": 1, "write": 1, "create": 1}
        ]
    }

    # Reorder so dependency doctypes exist before link references
    all_dts = [
        joint_signatory_dt,
        beneficiary_dt,
        required_doc_dt,
        risk_profile_dt,
        pep_sanction_dt,
        suspicious_rule_dt,
        crm_sla_dt,
        investor_app_dt,
        investor_kyc_dt,
        investor_master_dt,
        suspicious_log_dt,
        interaction_dt
    ]

    for dt in all_dts:
        make_doctype(dt)

def seed_sprint1_data():
    print("\n=== SEEDING SPRINT 1 DATA ===")

    # 1. Required Documents Setup
    req_docs = [
        {"document_code": "NAT_ID", "document_name": "National Identification Card (NIN)", "mandatory": 1, "investor_type": "Individual"},
        {"document_code": "PASSPORT", "document_name": "Valid Passport (Foreign / Non-resident)", "mandatory": 0, "investor_type": "Individual"},
        {"document_code": "PROOF_ADDR", "document_name": "Proof of Address (Utility Bill / Bank Statement)", "mandatory": 1, "investor_type": "All"},
        {"document_code": "TIN_CERT", "document_name": "URA Tax Identification Number (TIN) Certificate", "mandatory": 1, "investor_type": "All"},
        {"document_code": "CERT_INCORP", "document_name": "Certificate of Incorporation / Registration", "mandatory": 1, "investor_type": "Corporate"},
        {"document_code": "MEM_ARTICLES", "document_name": "Memorandum and Articles of Association", "mandatory": 1, "investor_type": "Corporate"},
        {"document_code": "BOARD_RESOL", "document_name": "Board Resolution Mandating Account Opening", "mandatory": 1, "investor_type": "Corporate"},
        {"document_code": "TRUST_DEED", "document_name": "Registered Trust Deed / Scheme Rules", "mandatory": 1, "investor_type": "Trust / Institutional"}
    ]
    for d in req_docs:
        if not frappe.db.exists("Asset Required Document", d["document_code"]):
            doc = frappe.new_doc("Asset Required Document")
            doc.update(d)
            doc.insert(ignore_permissions=True)
            print(f"Seeded Required Document: {d['document_code']}")

    # 2. Risk Profiles
    profiles = [
        {"code": "LOW_RISK", "risk_tier": "Low", "lower_score": 0.0, "upper_score": 30.0, "review_frequency_months": 24, "description": "Standard retail investors with domestic verified income."},
        {"code": "MED_RISK", "risk_tier": "Medium", "lower_score": 30.1, "upper_score": 60.0, "review_frequency_months": 12, "description": "High net worth or cross-border non-resident retail clients."},
        {"code": "HIGH_RISK", "risk_tier": "High", "lower_score": 60.1, "upper_score": 100.0, "review_frequency_months": 6, "description": "PEP, sanctioned entities, complex corporate structures requiring CE approval."}
    ]
    for p in profiles:
        if not frappe.db.exists("Asset Risk Profile", p["code"]):
            doc = frappe.new_doc("Asset Risk Profile")
            doc.update(p)
            doc.insert(ignore_permissions=True)
            print(f"Seeded Risk Profile: {p['code']}")

    # 3. PEP Sanctions Setup
    pep_rules = [
        {"rule_code": "PEP_MATCH", "risk_type": "PEP", "is_match": 1, "risk_score_impact": 40.0, "requires_ce_approval": 1, "description": "Client identified as Politically Exposed Person."},
        {"rule_code": "SANCTION_MATCH", "risk_type": "SANCTION", "is_match": 1, "risk_score_impact": 50.0, "requires_ce_approval": 1, "description": "Client matches OFAC / UN / National Sanction list."}
    ]
    for pr in pep_rules:
        if not frappe.db.exists("Asset PEP Sanction Setup", pr["rule_code"]):
            doc = frappe.new_doc("Asset PEP Sanction Setup")
            doc.update(pr)
            doc.insert(ignore_permissions=True)
            print(f"Seeded PEP/Sanction Rule: {pr['rule_code']}")

    # 4. Suspicious Transaction Rules
    aml_rules = [
        {"rule_id": "AML_LARGE_CASH", "rule_name": "Large Cash Transaction Threshold", "rule_type": "Large Cash Transaction", "threshold_amount": 20000000, "threshold_days": 1, "active": 1, "description": "Deposits >= 20,000,000 UGX within 24 hours."},
        {"rule_id": "AML_RAPID_EXIT", "rule_name": "Rapid Full Redemption Within 7 Days", "rule_type": "Rapid Full Redemption", "threshold_amount": 10000000, "threshold_days": 7, "active": 1, "description": "Subscribes and requests full exit within 7 days."}
    ]
    for r in aml_rules:
        if not frappe.db.exists("Asset Suspicious Transaction Rule", r["rule_id"]):
            doc = frappe.new_doc("Asset Suspicious Transaction Rule")
            doc.update(r)
            doc.insert(ignore_permissions=True)
            print(f"Seeded AML Rule: {r['rule_id']}")

    # 5. CRM SLA Setup
    slas = [
        {"code": "SLA_STATEMENT", "category": "Account Statement Request", "functional_group": "Client Service", "internal_sla_hours": 2, "external_sla_hours": 4, "active": 1, "description": "Dispatch of client statement and portfolio holding summary."},
        {"code": "SLA_INQUIRY", "category": "General Inquiry", "functional_group": "Client Service", "internal_sla_hours": 4, "external_sla_hours": 24, "active": 1, "description": "Standard client product and performance inquiry."},
        {"code": "SLA_SUB_ISSUE", "category": "Subscription Follow-up", "functional_group": "Operations", "internal_sla_hours": 4, "external_sla_hours": 24, "active": 1, "description": "Tracing unallocated deposits and unit allotment."},
        {"code": "SLA_RED_ISSUE", "category": "Redemption Follow-up", "functional_group": "Operations", "internal_sla_hours": 4, "external_sla_hours": 48, "active": 1, "description": "Payment status follow-up for unit redemption."},
        {"code": "SLA_SWITCH", "category": "Fund Switch Request", "functional_group": "Operations", "internal_sla_hours": 4, "external_sla_hours": 24, "active": 1, "description": "Processing switch from Money Market to Bond / Equity Fund."},
        {"code": "SLA_COMPLAINT", "category": "Client Complaint", "functional_group": "Client Service", "internal_sla_hours": 2, "external_sla_hours": 24, "active": 1, "description": "Formal complaint regarding service or delays requiring escalation."}
    ]
    for s in slas:
        if not frappe.db.exists("Asset CRM SLA Setup", s["code"]):
            doc = frappe.new_doc("Asset CRM SLA Setup")
            doc.update(s)
            doc.insert(ignore_permissions=True)
            print(f"Seeded CRM SLA: {s['code']}")

    frappe.db.commit()
    print("All Sprint 1 seed data committed successfully!")

def main():
    make_roles()
    setup_sprint1_doctypes()
    seed_sprint1_data()

if __name__ == "__main__":
    main()
