import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime, add_to_date

class AssetClientInteraction(Document):
    def before_insert(self):
        if not self.date_opened:
            self.date_opened = now_datetime()
        self.populate_investor_details()
        self.calculate_sla()

    def validate(self):
        self.populate_investor_details()
        if not self.target_due_datetime:
            self.calculate_sla()
        self.check_sla_breach()

    def populate_investor_details(self):
        if self.investor and not self.investor_name:
            self.investor_name = frappe.db.get_value("Asset Investor", self.investor, "investor_name")

    def calculate_sla(self):
        """Calculates SLA target due date based on setup hours (Chapter 4.6)."""
        if self.sla_setup:
            sla_doc = frappe.get_doc("Asset CRM SLA Setup", self.sla_setup)
            hours = sla_doc.internal_sla_hours or 4
            opened = get_datetime(self.date_opened or now_datetime())
            self.target_due_datetime = add_to_date(opened, hours=hours)

    def check_sla_breach(self):
        """Monitors SLA deadlines and escalates overdue cases (Chapter 4.6)."""
        if self.status not in ("Resolved", "Closed") and self.target_due_datetime:
            if now_datetime() > get_datetime(self.target_due_datetime):
                self.is_overdue = 1
                if self.escalation_level == "Level 1 (Staff)":
                    self.escalation_level = "Level 2 (Team Leader)"
                    self.status = "Escalated"
            else:
                self.is_overdue = 0

    @frappe.whitelist()
    def resolve_case(self, resolution_summary, resolved_by=None):
        """Resolves case and logs resolution summary (Chapter 4.5)."""
        self.status = "Resolved"
        self.resolution_datetime = now_datetime()
        self.resolved_by = resolved_by or frappe.session.user
        self.resolution_summary = resolution_summary
        self.save(ignore_permissions=True)
        return {"status": self.status, "resolution_datetime": self.resolution_datetime}

    @frappe.whitelist()
    def close_case(self, client_feedback="Satisfied", feedback_comments=None):
        """Closes case with recorded client feedback (Chapter 4.5)."""
        if self.status != "Resolved":
            self.status = "Resolved"
            self.resolution_datetime = now_datetime()
            self.resolved_by = frappe.session.user
        self.status = "Closed"
        self.client_feedback = client_feedback
        self.feedback_comments = feedback_comments
        self.save(ignore_permissions=True)
        return {"status": self.status, "client_feedback": self.client_feedback}

    @frappe.whitelist()
    def reopen_case(self, reason):
        """Reopens a case when client feedback indicates dissatisfaction (Chapter 4.5)."""
        self.status = "In Progress"
        self.resolution_datetime = None
        self.client_feedback = "Dissatisfied"
        if self.feedback_comments:
            self.feedback_comments += f"\nReopened: {reason}"
        else:
            self.feedback_comments = f"Reopened: {reason}"
        self.escalation_level = "Level 2 (Team Leader)"
        self.save(ignore_permissions=True)
        return {"status": self.status, "escalation_level": self.escalation_level}
