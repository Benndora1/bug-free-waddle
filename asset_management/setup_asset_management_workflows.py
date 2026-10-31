import frappe

def create_workflows():
    # 1. Ensure Workflow States
    states = [
        {"name": "Draft", "style": "Warning"},
        {"name": "Pending Approval", "style": "Primary"},
        {"name": "Approved", "style": "Success"},
        {"name": "Rejected", "style": "Danger"},
        {"name": "Submitted", "style": "Success"},
        {"name": "Cancelled", "style": "Danger"}
    ]
    for s in states:
        if not frappe.db.exists("Workflow State", s["name"]):
            ws = frappe.new_doc("Workflow State")
            ws.workflow_state_name = s["name"]
            ws.style = s["style"]
            ws.insert(ignore_permissions=True)
            print(f"Created Workflow State: {s['name']}")

    # 2. Ensure Workflow Action Masters
    actions = [
        "Submit for Review",
        "Approve",
        "Reject",
        "Resubmit",
        "Post & Issue Units",
        "Post & Liquidate Units",
        "Post & Execute Switch",
        "Submit for Verification",
        "Approve NAV",
        "Reject NAV",
        "Publish & Post NAV",
        "Submit for Authorization",
        "Approve Trade",
        "Reject Trade",
        "Execute & Dispatch Custody",
        "Authorize & Sign",
        "Reject Instruction",
        "Dispatch to Custodian",
        "Submit for Compliance Review",
        "Approve KYC",
        "Reject KYC",
        "Generate Investor Master",
        "Submit Reconciliation",
        "Sign Off Reconciliation",
        "Reject Reconciliation",
        "Post Reconciled Batches"
    ]
    for a in actions:
        if not frappe.db.exists("Workflow Action Master", a):
            wa = frappe.new_doc("Workflow Action Master")
            wa.workflow_action_name = a
            wa.insert(ignore_permissions=True)
            print(f"Created Workflow Action Master: {a}")

    # 3. Create Workflows
    workflow_defs = [
        {
            "workflow_name": "Asset Subscription Approval Workflow",
            "document_type": "Asset Subscription",
            "workflow_state_field": "workflow_state",
            "is_active": 1,
            "states": [
                {"state": "Draft", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Pending Approval", "doc_status": "0", "allow_edit": "Asset Fund Administrator"},
                {"state": "Approved", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Rejected", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Submitted", "doc_status": "1", "allow_edit": "Asset Management Admin"},
            ],
            "transitions": [
                {"state": "Draft", "action": "Submit for Review", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Draft", "action": "Submit for Review", "next_state": "Pending Approval", "allowed": "Asset Client Service"},
                {"state": "Draft", "action": "Approve", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "Asset Fund Administrator"},
                {"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "Asset Compliance Officer"},
                {"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "Asset Fund Administrator"},
                {"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "Asset Compliance Officer"},
                {"state": "Rejected", "action": "Resubmit", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Post & Issue Units", "next_state": "Submitted", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Post & Issue Units", "next_state": "Submitted", "allowed": "Asset Fund Administrator"},
                {"state": "Approved", "action": "Post & Issue Units", "next_state": "Submitted", "allowed": "Asset Management Admin"},
            ]
        },
        {
            "workflow_name": "Asset Redemption Approval Workflow",
            "document_type": "Asset Redemption",
            "workflow_state_field": "workflow_state",
            "is_active": 1,
            "states": [
                {"state": "Draft", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Pending Approval", "doc_status": "0", "allow_edit": "Asset Fund Administrator"},
                {"state": "Approved", "doc_status": "0", "allow_edit": "Asset Finance Officer"},
                {"state": "Rejected", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Submitted", "doc_status": "1", "allow_edit": "Asset Management Admin"},
            ],
            "transitions": [
                {"state": "Draft", "action": "Submit for Review", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Draft", "action": "Submit for Review", "next_state": "Pending Approval", "allowed": "Asset Client Service"},
                {"state": "Draft", "action": "Approve", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "Asset Fund Administrator"},
                {"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "Asset Compliance Officer"},
                {"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "Asset Fund Administrator"},
                {"state": "Rejected", "action": "Resubmit", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Post & Liquidate Units", "next_state": "Submitted", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Post & Liquidate Units", "next_state": "Submitted", "allowed": "Asset Finance Officer"},
                {"state": "Approved", "action": "Post & Liquidate Units", "next_state": "Submitted", "allowed": "Asset Management Admin"},
            ]
        },
        {
            "workflow_name": "Asset Fund Switch Approval Workflow",
            "document_type": "Asset Fund Switch",
            "workflow_state_field": "workflow_state",
            "is_active": 1,
            "states": [
                {"state": "Draft", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Pending Approval", "doc_status": "0", "allow_edit": "Asset Fund Administrator"},
                {"state": "Approved", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Rejected", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Submitted", "doc_status": "1", "allow_edit": "Asset Management Admin"},
            ],
            "transitions": [
                {"state": "Draft", "action": "Submit for Review", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Draft", "action": "Approve", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Approve", "next_state": "Approved", "allowed": "Asset Fund Administrator"},
                {"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Reject", "next_state": "Rejected", "allowed": "Asset Fund Administrator"},
                {"state": "Rejected", "action": "Resubmit", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Post & Execute Switch", "next_state": "Submitted", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Post & Execute Switch", "next_state": "Submitted", "allowed": "Asset Fund Administrator"},
                {"state": "Approved", "action": "Post & Execute Switch", "next_state": "Submitted", "allowed": "Asset Management Admin"},
            ]
        },
        {
            "workflow_name": "Asset Fund Valuation Workflow",
            "document_type": "Asset Fund Valuation",
            "workflow_state_field": "workflow_state",
            "is_active": 1,
            "states": [
                {"state": "Draft", "doc_status": "0", "allow_edit": "Asset Fund Administrator"},
                {"state": "Pending Approval", "doc_status": "0", "allow_edit": "Asset Investment Manager"},
                {"state": "Approved", "doc_status": "0", "allow_edit": "Asset Fund Administrator"},
                {"state": "Rejected", "doc_status": "0", "allow_edit": "Asset Fund Administrator"},
                {"state": "Submitted", "doc_status": "1", "allow_edit": "Asset Management Admin"},
            ],
            "transitions": [
                {"state": "Draft", "action": "Submit for Verification", "next_state": "Pending Approval", "allowed": "Asset Fund Administrator"},
                {"state": "Draft", "action": "Approve NAV", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Approve NAV", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Approve NAV", "next_state": "Approved", "allowed": "Asset Investment Manager"},
                {"state": "Pending Approval", "action": "Reject NAV", "next_state": "Rejected", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Reject NAV", "next_state": "Rejected", "allowed": "Asset Investment Manager"},
                {"state": "Rejected", "action": "Resubmit", "next_state": "Pending Approval", "allowed": "Asset Fund Administrator"},
                {"state": "Approved", "action": "Publish & Post NAV", "next_state": "Submitted", "allowed": "Asset Fund Administrator"},
                {"state": "Approved", "action": "Publish & Post NAV", "next_state": "Submitted", "allowed": "Asset Management Admin"},
            ]
        },
        {
            "workflow_name": "Asset Trade Order Workflow",
            "document_type": "Asset Trade Order Header",
            "workflow_state_field": "workflow_state",
            "is_active": 1,
            "states": [
                {"state": "Draft", "doc_status": "0", "allow_edit": "Asset Investment Manager"},
                {"state": "Pending Approval", "doc_status": "0", "allow_edit": "Asset Compliance Officer"},
                {"state": "Approved", "doc_status": "0", "allow_edit": "Asset Investment Manager"},
                {"state": "Rejected", "doc_status": "0", "allow_edit": "Asset Investment Manager"},
                {"state": "Submitted", "doc_status": "1", "allow_edit": "Asset Management Admin"},
            ],
            "transitions": [
                {"state": "Draft", "action": "Submit for Authorization", "next_state": "Pending Approval", "allowed": "Asset Investment Manager"},
                {"state": "Draft", "action": "Submit for Authorization", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Draft", "action": "Approve Trade", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Approve Trade", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Approve Trade", "next_state": "Approved", "allowed": "Asset Compliance Officer"},
                {"state": "Pending Approval", "action": "Approve Trade", "next_state": "Approved", "allowed": "Asset Investment Manager"},
                {"state": "Pending Approval", "action": "Reject Trade", "next_state": "Rejected", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Reject Trade", "next_state": "Rejected", "allowed": "Asset Compliance Officer"},
                {"state": "Rejected", "action": "Resubmit", "next_state": "Pending Approval", "allowed": "Asset Investment Manager"},
                {"state": "Approved", "action": "Execute & Dispatch Custody", "next_state": "Submitted", "allowed": "Asset Investment Manager"},
                {"state": "Approved", "action": "Execute & Dispatch Custody", "next_state": "Submitted", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Execute & Dispatch Custody", "next_state": "Submitted", "allowed": "Asset Management Admin"},
            ]
        },
        {
            "workflow_name": "Asset Custody Instruction Workflow",
            "document_type": "Asset Custody Instruction",
            "workflow_state_field": "workflow_state",
            "is_active": 1,
            "states": [
                {"state": "Draft", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Pending Approval", "doc_status": "0", "allow_edit": "Asset Fund Administrator"},
                {"state": "Approved", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Rejected", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Submitted", "doc_status": "1", "allow_edit": "Asset Management Admin"},
            ],
            "transitions": [
                {"state": "Draft", "action": "Submit for Verification", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Draft", "action": "Authorize & Sign", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Authorize & Sign", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Authorize & Sign", "next_state": "Approved", "allowed": "Asset Fund Administrator"},
                {"state": "Pending Approval", "action": "Reject Instruction", "next_state": "Rejected", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Reject Instruction", "next_state": "Rejected", "allowed": "Asset Fund Administrator"},
                {"state": "Rejected", "action": "Resubmit", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Dispatch to Custodian", "next_state": "Submitted", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Dispatch to Custodian", "next_state": "Submitted", "allowed": "Asset Fund Administrator"},
                {"state": "Approved", "action": "Dispatch to Custodian", "next_state": "Submitted", "allowed": "Asset Management Admin"},
            ]
        },
        {
            "workflow_name": "Asset Investor Application Workflow",
            "document_type": "Asset Investor Application",
            "workflow_state_field": "workflow_state",
            "is_active": 1,
            "states": [
                {"state": "Draft", "doc_status": "0", "allow_edit": "Asset Client Service"},
                {"state": "Pending Approval", "doc_status": "0", "allow_edit": "Asset Compliance Officer"},
                {"state": "Approved", "doc_status": "0", "allow_edit": "Asset Compliance Officer"},
                {"state": "Rejected", "doc_status": "0", "allow_edit": "Asset Client Service"},
                {"state": "Submitted", "doc_status": "1", "allow_edit": "Asset Management Admin"},
            ],
            "transitions": [
                {"state": "Draft", "action": "Submit for Compliance Review", "next_state": "Pending Approval", "allowed": "Asset Client Service"},
                {"state": "Draft", "action": "Submit for Compliance Review", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Draft", "action": "Approve KYC", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Approve KYC", "next_state": "Approved", "allowed": "Asset Compliance Officer"},
                {"state": "Pending Approval", "action": "Approve KYC", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Reject KYC", "next_state": "Rejected", "allowed": "Asset Compliance Officer"},
                {"state": "Pending Approval", "action": "Reject KYC", "next_state": "Rejected", "allowed": "Asset Management Admin"},
                {"state": "Rejected", "action": "Resubmit", "next_state": "Pending Approval", "allowed": "Asset Client Service"},
                {"state": "Rejected", "action": "Resubmit", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Generate Investor Master", "next_state": "Submitted", "allowed": "Asset Compliance Officer"},
                {"state": "Approved", "action": "Generate Investor Master", "next_state": "Submitted", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Generate Investor Master", "next_state": "Submitted", "allowed": "Asset Management Admin"},
            ]
        },
        {
            "workflow_name": "Asset BOL Import Workflow",
            "document_type": "Asset BOL Import Header",
            "workflow_state_field": "workflow_state",
            "is_active": 1,
            "states": [
                {"state": "Draft", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Pending Approval", "doc_status": "0", "allow_edit": "Asset Finance Officer"},
                {"state": "Approved", "doc_status": "0", "allow_edit": "Asset Finance Officer"},
                {"state": "Rejected", "doc_status": "0", "allow_edit": "Asset Management Operations"},
                {"state": "Submitted", "doc_status": "1", "allow_edit": "Asset Management Admin"},
            ],
            "transitions": [
                {"state": "Draft", "action": "Submit Reconciliation", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Draft", "action": "Sign Off Reconciliation", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Sign Off Reconciliation", "next_state": "Approved", "allowed": "Asset Finance Officer"},
                {"state": "Pending Approval", "action": "Sign Off Reconciliation", "next_state": "Approved", "allowed": "Asset Fund Administrator"},
                {"state": "Pending Approval", "action": "Sign Off Reconciliation", "next_state": "Approved", "allowed": "Asset Management Admin"},
                {"state": "Pending Approval", "action": "Reject Reconciliation", "next_state": "Rejected", "allowed": "Asset Finance Officer"},
                {"state": "Pending Approval", "action": "Reject Reconciliation", "next_state": "Rejected", "allowed": "Asset Fund Administrator"},
                {"state": "Rejected", "action": "Resubmit", "next_state": "Pending Approval", "allowed": "Asset Management Operations"},
                {"state": "Approved", "action": "Post Reconciled Batches", "next_state": "Submitted", "allowed": "Asset Finance Officer"},
                {"state": "Approved", "action": "Post Reconciled Batches", "next_state": "Submitted", "allowed": "Asset Management Admin"},
            ]
        }
    ]

    for wf_data in workflow_defs:
        wf_name = wf_data["workflow_name"]
        if frappe.db.exists("Workflow", wf_name):
            doc = frappe.get_doc("Workflow", wf_name)
            doc.states = []
            doc.transitions = []
        else:
            doc = frappe.new_doc("Workflow")
            doc.workflow_name = wf_name

        doc.document_type = wf_data["document_type"]
        doc.workflow_state_field = wf_data["workflow_state_field"]
        doc.is_active = wf_data["is_active"]

        for st in wf_data["states"]:
            doc.append("states", st)
        for tr in wf_data["transitions"]:
            doc.append("transitions", tr)

        doc.save(ignore_permissions=True)
        print(f"Configured Workflow: {wf_name}")

    frappe.db.commit()
    print("All Asset Management Workflows configured successfully!")

if __name__ == "__main__":
    create_workflows()
