"""Integration tests for Asset Client Interaction DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from asset_management.tests.factories import make_investor

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetClientInteraction(IntegrationTestCase):
	def test_interaction_sla_and_resolution(self) -> None:
		inv = make_investor()
		ci = frappe.new_doc("Asset Client Interaction")
		ci.date_opened = now_datetime()
		ci.investor = inv.name
		ci.channel = "Email"
		ci.sla_setup = "SLA_STATEMENT"
		ci.subject = "Statement Request"
		ci.description = "Requesting monthly statement"
		# Test setup: ignore_permissions required
		ci.insert(ignore_permissions=True)

		self.assertEqual(ci.status, "Open")
		self.assertIsNotNone(ci.target_due_datetime)

		res = ci.resolve_case(resolution_summary="Statement sent via email.")
		self.assertEqual(res["status"], "Resolved")
