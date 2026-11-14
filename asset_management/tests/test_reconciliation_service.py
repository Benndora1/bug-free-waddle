import unittest
from decimal import Decimal

from asset_management.services.reconciliation import calculate_reconciliation_metrics


class TestReconciliationService(unittest.TestCase):
	def test_01_pure_reconciliation_metrics_exact_and_within_tolerance(self) -> None:
		"""Verify register_value = units x nav (2 dp), gl_net_assets = assets - liabilities, difference, within_tolerance."""
		# 1. Exact match: 100,000.000000 units @ 100.054795 = 10,005,479.50
		res = calculate_reconciliation_metrics(
			units_in_issue=Decimal("100000.000000"),
			nav_per_unit=Decimal("100.054795"),
			gl_total_assets=Decimal("10010958.95"),
			gl_total_liabilities=Decimal("5479.45"),
			tolerance=Decimal("0.05"),
		)
		self.assertEqual(res["units_in_issue"], Decimal("100000.000000"))
		self.assertEqual(res["nav_per_unit"], Decimal("100.054795"))
		self.assertEqual(res["register_value"], Decimal("10005479.50"))
		self.assertEqual(res["gl_net_assets"], Decimal("10005479.50"))
		self.assertEqual(res["difference"], Decimal("0.00"))
		self.assertTrue(res["within_tolerance"])

		# 2. Small rounding difference within 0.05 tolerance
		res_tol = calculate_reconciliation_metrics(
			units_in_issue=Decimal("100000.000000"),
			nav_per_unit=Decimal("100.054795"),
			gl_total_assets=Decimal("10010958.92"),
			gl_total_liabilities=Decimal("5479.45"),
			tolerance=Decimal("0.05"),
		)
		self.assertEqual(res_tol["difference"], Decimal("0.03"))
		self.assertTrue(res_tol["within_tolerance"])

		# 3. Out of balance difference > tolerance
		res_fail = calculate_reconciliation_metrics(
			units_in_issue=Decimal("100000.000000"),
			nav_per_unit=Decimal("100.054795"),
			gl_total_assets=Decimal("10060958.95"),
			gl_total_liabilities=Decimal("5479.45"),
			tolerance=Decimal("0.05"),
		)
		self.assertEqual(res_fail["difference"], Decimal("-50000.00"))
		self.assertFalse(res_fail["within_tolerance"])
