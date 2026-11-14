"""Integration tests for Asset CRM SLA Setup DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from asset_management.tests.factories import make_investor

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetCRMSLASetup(IntegrationTestCase):
	def test_custom_sla_setup_computes_target_due_datetime(self) -> None:
		if not frappe.db.exists("Asset CRM SLA Setup", "SLA_TEST_4H"):
			sla = frappe.new_doc("Asset CRM SLA Setup")
			sla.code = "SLA_TEST_4H"
			sla.inquiry_type = "Custom Inquiry"
			sla.target_resolution_hours = 4.0
			sla.escalation_role = "Asset Client Service"
			# Test setup: ignore_permissions required
			sla.insert(ignore_permissions=True)

		inv = make_investor()
		opened = add_to_date(now_datetime(), hours=-6)
		ci = frappe.new_doc("Asset Client Interaction")
		ci.date_opened = opened
		ci.investor = inv.name
		ci.channel = "Phone Call"
		ci.sla_setup = "SLA_TEST_4H"
		ci.subject = "Overdue Custom SLA"
		ci.description = "Client waiting for custom SLA response."
		# Test setup: ignore_permissions required
		ci.insert(ignore_permissions=True)

		self.assertEqual(ci.is_overdue, 1)
		self.assertEqual(ci.status, "Escalated")
