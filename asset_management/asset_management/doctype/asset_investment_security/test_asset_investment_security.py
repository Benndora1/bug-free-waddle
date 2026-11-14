"""Integration tests for Asset Investment Security DocType."""

from frappe.tests import IntegrationTestCase

from asset_management.tests.factories import make_security

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetInvestmentSecurity(IntegrationTestCase):
	def test_bond_generates_coupon_schedule(self) -> None:
		sec = make_security(
			security_code="TEST-DT-BOND-2030",
			security_name="Test 12% Bond 2030",
			instrument_type="Treasury Bond",
			asset_class="Treasury Bond",
			issue_date="2025-01-01",
			maturity_date="2030-01-01",
			coupon_rate=12.0,
			coupon_rate_pct=12.0,
			coupon_frequency="Semi-Annual",
		)
		self.assertGreaterEqual(len(sec.coupon_schedule), 8)
		self.assertEqual(sec.coupon_schedule[0].coupon_rate, 6.0)
