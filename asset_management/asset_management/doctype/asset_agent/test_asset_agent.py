"""Integration tests for Asset Agent DocType."""

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.tests.factories import make_agent

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetAgent(IntegrationTestCase):
	def test_agent_creation_and_commission_rates(self) -> None:
		ag = make_agent(
			agent_code="AGT-DT-001",
			agent_name="Advisory Partners Ltd",
			commission_rate_pct=1.25,
		)
		self.assertTrue(frappe.db.exists("Asset Agent", ag.name))
		self.assertEqual(ag.commission_rate_pct, 1.25)
		self.assertEqual(ag.status, "Active")
