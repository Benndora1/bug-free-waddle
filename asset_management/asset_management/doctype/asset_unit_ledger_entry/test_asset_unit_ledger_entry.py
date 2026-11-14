"""Integration tests for Asset Unit Ledger Entry."""

import unittest
from decimal import Decimal

import frappe
from frappe.tests import UnitTestCase

from asset_management.services.units import get_unit_balance


class TestAssetUnitLedgerEntry(UnitTestCase):
	def test_immutability_guard(self):
		"""Verify that editing critical fields on an existing ledger entry is blocked."""
		entry = frappe.new_doc("Asset Unit Ledger Entry")
		entry.posting_date = "2026-11-14"
		entry.investor = "__TEST_IMMUTABLE_INV"
		entry.fund = "SBG-MMF"
		entry.voucher_type = "Asset Subscription"
		entry.voucher_no = "TEST-SUB-001"
		entry.entry_type = "Subscription"
		entry.units = 100.0
		entry.price_per_unit = 100.0
		entry.amount = 10000.0
		entry.flags.ignore_links = True
		entry.insert(ignore_permissions=True)

		# Attempt to edit units
		entry.units = 200.0
		with self.assertRaises(frappe.ValidationError):
			entry.save()

		# Clean up
		frappe.db.delete("Asset Unit Ledger Entry", {"name": entry.name})
