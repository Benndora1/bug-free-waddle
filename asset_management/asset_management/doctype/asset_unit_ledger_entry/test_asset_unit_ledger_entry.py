"""Integration tests for Asset Unit Ledger Entry DocType."""

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.tests.factories import (
	make_checker_user,
	make_fund,
	make_investor,
	make_subscription,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetUnitLedgerEntry(IntegrationTestCase):
	def test_unit_ledger_entry_immutability_blocks_deletion(self) -> None:
		checker = make_checker_user()
		fund = make_fund(fund_id="TEST-ULE-DT", nav=100.0)
		inv = make_investor()

		sub = make_subscription(inv.name, fund.name, amount=200000.0, checker_user=checker)
		ule_name = frappe.db.get_value(
			"Asset Unit Ledger Entry", {"voucher_no": sub.name, "is_cancelled": 0}, "name"
		)
		self.assertTrue(bool(ule_name))

		ule_doc = frappe.get_doc("Asset Unit Ledger Entry", ule_name)
		with self.assertRaises(frappe.ValidationError):
			ule_doc.delete()
