"""Integration tests for Asset Security Price DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from asset_management.tests.factories import make_security, make_security_price

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetSecurityPrice(IntegrationTestCase):
	def test_security_price_updates_security_market_price_and_rejects_duplicate_date(self) -> None:
		sec = make_security(security_code="TEST-SP-SEC-01", current_market_price=100.0)
		sp = make_security_price(
			security=sec.name,
			price_date="2026-10-15",
			clean_price=104.25,
			yield_pct=9.5,
		)
		self.assertEqual(flt(sp.clean_price, 6), 104.25)

		sec.reload()
		self.assertEqual(flt(sec.current_market_price, 6), 104.25)

		dup = frappe.new_doc("Asset Security Price")
		dup.security = sec.name
		dup.price_date = "2026-10-15"
		dup.clean_price = 105.0
		with self.assertRaises((frappe.ValidationError, frappe.DuplicateEntryError)):
			dup.insert(ignore_permissions=True)
