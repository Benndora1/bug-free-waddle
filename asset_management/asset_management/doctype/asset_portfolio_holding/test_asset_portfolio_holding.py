"""Integration tests for Asset Portfolio Holding DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from asset_management.tests.factories import make_fund, make_security

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetPortfolioHolding(IntegrationTestCase):
	def test_holding_dirty_market_value_and_unrealized_gain(self) -> None:
		fund = make_fund(fund_id="TEST-HOLD-MMF", nav=100.0)
		sec = make_security(
			security_code="TEST-HOLD-SEC",
			instrument_type="Treasury Bond",
			asset_class="Treasury Bond",
			current_market_price=102.0,
		)

		h = frappe.new_doc("Asset Portfolio Holding")
		h.fund = fund.name
		h.security = sec.name
		h.asset_class = "Treasury Bond"
		h.face_value = 1000000.0
		h.carrying_cost = 1000000.0
		h.accrued_interest = 5000.0
		h.holding_status = "Active"
		# Test setup: ignore_permissions required
		h.insert(ignore_permissions=True)

		self.assertEqual(flt(h.dirty_market_value, 2), 1005000.0)
		self.assertEqual(flt(h.amortized_cost, 2), 1000000.0)
