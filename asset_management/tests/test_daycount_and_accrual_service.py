"""Unit tests for day-count conventions and fee accruals (services/daycount.py, services/accrual.py)."""

from datetime import date
from decimal import Decimal

from frappe.tests import UnitTestCase

from asset_management.services.accrual import (
	FeeRule,
	calculate_fee_accrual,
	calculate_fund_fee_accruals,
)
from asset_management.services.daycount import previous_business_day, year_fraction


class TestDaycountAndAccrualService(UnitTestCase):
	def test_01_daycount_conventions(self) -> None:
		"""Verify ACT/365F, ACT/360, ACT/ACT, and 30/360 year fractions."""
		yf_1d = year_fraction(date(2026, 11, 5), date(2026, 11, 6), "ACT/365F")
		self.assertEqual(yf_1d, Decimal("1") / Decimal("365"))

		yf_3d = year_fraction(date(2026, 11, 6), date(2026, 11, 9), "ACT/365F")
		self.assertEqual(yf_3d, Decimal("3") / Decimal("365"))

		yf_360 = year_fraction(date(2026, 11, 1), date(2026, 12, 1), "ACT/360")
		self.assertEqual(yf_360, Decimal("30") / Decimal("360"))

		yf_act_2026 = year_fraction(date(2026, 3, 1), date(2026, 3, 11), "ACT/ACT")
		self.assertEqual(yf_act_2026, Decimal("10") / Decimal("365"))

		yf_act_2024 = year_fraction(date(2024, 2, 20), date(2024, 3, 1), "ACT/ACT")
		self.assertEqual(yf_act_2024, Decimal("10") / Decimal("366"))

		yf_30_360 = year_fraction(date(2026, 1, 15), date(2026, 2, 15), "30/360")
		self.assertEqual(yf_30_360, Decimal("30") / Decimal("360"))

	def test_02_exact_gav_management_fee_1_day_and_3_days(self) -> None:
		"""Exact R-11 requirement:
		GAV 100,000,000.00, management fee 2% ACT/365F:
		- one day -> 5,479.45
		- Friday to Monday (3 days) -> 16,438.36
		"""
		gav = Decimal("100000000.00")
		rate = Decimal("2.0")

		fee_1d = calculate_fee_accrual(
			basis_amount=gav,
			annual_rate_pct=rate,
			start_date=date(2026, 11, 5),
			end_date=date(2026, 11, 6),
			day_count="ACT/365F",
		)
		self.assertEqual(fee_1d, Decimal("5479.45"))

		fee_3d = calculate_fee_accrual(
			basis_amount=gav,
			annual_rate_pct=rate,
			start_date=date(2026, 11, 6),
			end_date=date(2026, 11, 9),
			day_count="ACT/365F",
		)
		self.assertEqual(fee_3d, Decimal("16438.36"))

	def test_03_prior_nav_vs_gav_fee_rules_and_previous_business_day(self) -> None:
		"""Verify fee rules using Prior NAV vs GAV and previous_business_day across weekends."""
		rules = [
			FeeRule(
				fee_type="Management Fee",
				basis_type="GAV",
				annual_rate_pct=Decimal("2.0"),
				day_count="ACT/365F",
			),
			FeeRule(
				fee_type="Custody Fee",
				basis_type="Prior NAV",
				annual_rate_pct=Decimal("0.36"),
				day_count="ACT/360",
			),
		]
		res = calculate_fund_fee_accruals(
			rules=rules,
			gav=Decimal("100000000.00"),
			prior_nav=Decimal("90000000.00"),
			start_date=date(2026, 11, 5),
			end_date=date(2026, 11, 6),
		)
		self.assertEqual(res["Management Fee"], Decimal("5479.45"))
		self.assertEqual(res["Custody Fee"], Decimal("900.00"))
		self.assertEqual(res["total"], Decimal("6379.45"))

		self.assertEqual(previous_business_day(date(2026, 11, 9)), date(2026, 11, 6))
		self.assertEqual(previous_business_day(date(2026, 11, 10)), date(2026, 11, 9))
