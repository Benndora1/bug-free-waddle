"""Integration tests for Asset Investor DocType (ADR-0002 Supplier link)."""

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.tests.factories import make_investor

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetInvestor(IntegrationTestCase):
	def test_investor_auto_creates_and_syncs_unit_holder_supplier(self) -> None:
		inv = make_investor(investor_name="Supplier Sync Client")
		self.assertTrue(bool(inv.supplier))
		self.assertTrue(frappe.db.exists("Supplier", inv.supplier))

		sup = frappe.get_doc("Supplier", inv.supplier)
		self.assertEqual(sup.supplier_group, "Unit Holders")
		self.assertEqual(sup.supplier_name, "Supplier Sync Client")

		inv.investor_name = "Renamed Supplier Client"
		# Test setup: ignore_permissions required
		inv.save(ignore_permissions=True)
		sup.reload()
		self.assertEqual(sup.supplier_name, "Renamed Supplier Client")
