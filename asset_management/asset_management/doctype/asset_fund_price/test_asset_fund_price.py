"""Integration tests for Asset Fund Price DocType."""

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.tests.factories import make_fund

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetFundPrice(IntegrationTestCase):
	def test_direct_insert_blocked_without_valuation_submit_flag(self) -> None:
		fund = make_fund(fund_id="TEST-FP-MMF", nav=0.0)
		fp = frappe.new_doc("Asset Fund Price")
		fp.fund = fund.name
		fp.price_date = "2026-10-01"
		fp.nav_per_unit = 100.0
		fp.bid_price = 100.0
		fp.offer_price = 100.0
		with self.assertRaises(frappe.ValidationError):
			fp.insert(ignore_permissions=True)
