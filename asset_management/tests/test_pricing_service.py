"""Tests for pricing calculations and fund price resolution (services/pricing.py)."""

from decimal import Decimal

from frappe.tests import UnitTestCase

from asset_management.services.pricing import (
	calculate_redemption_pricing,
	calculate_subscription_pricing,
	calculate_units_for_redemption_amount,
)


class TestPricingService(UnitTestCase):
	def test_01_subscription_pricing_exact_numbers(self):
		"""Test exact subscription pricing:

		Gross 10,000,000.00, Fee 1%, Offer 115.452000:
		- Entry fee = 100,000.00
		- Net invested = 9,900,000.00
		- Units allocated = 85749.922045 (ROUND_DOWN)
		"""
		gross = Decimal("10000000.00")
		fee_rate = Decimal("1.0")  # 1%
		offer_price = Decimal("115.452000")

		result = calculate_subscription_pricing(gross, fee_rate, offer_price)

		self.assertEqual(result["entry_fee"], Decimal("100000.00"))
		self.assertEqual(result["net_amount"], Decimal("9900000.00"))
		self.assertEqual(result["units"], Decimal("85749.922045"))
		# 85749.922045 * 115.452000 = 9899999.9999399 -> 9900000.00 invested
		self.assertEqual(result["invested_cash"], Decimal("9900000.00"))
		self.assertEqual(result["residual_cash"], Decimal("0.00"))

	def test_02_subscription_pricing_rounding_and_residual_cash(self):
		"""Verify that ROUND_DOWN leaves any unallotted cents as client cash."""
		gross = Decimal("100000.00")
		fee_rate = Decimal("2.5")  # 2.5%
		offer_price = Decimal("13.333333")

		result = calculate_subscription_pricing(gross, fee_rate, offer_price)
		self.assertEqual(result["entry_fee"], Decimal("2500.00"))
		self.assertEqual(result["net_amount"], Decimal("97500.00"))
		# 97500 / 13.333333 = 7312.50018281... -> 7312.500182
		self.assertEqual(result["units"], Decimal("7312.500182"))
		self.assertLessEqual(result["invested_cash"], result["net_amount"])
		self.assertEqual(result["invested_cash"] + result["residual_cash"], result["net_amount"])

	def test_03_zero_fee_pricing(self):
		"""Zero fee should allocate entire gross amount."""
		gross = Decimal("5000000.00")
		fee_rate = Decimal("0.0")
		offer_price = Decimal("100.000000")

		result = calculate_subscription_pricing(gross, fee_rate, offer_price)
		self.assertEqual(result["entry_fee"], Decimal("0.00"))
		self.assertEqual(result["net_amount"], Decimal("5000000.00"))
		self.assertEqual(result["units"], Decimal("50000.000000"))
		self.assertEqual(result["residual_cash"], Decimal("0.00"))

	def test_04_redemption_pricing_exact_numbers(self):
		"""Redeem 4,000 units at bid 120.500000, exit fee 0.5%, WHT None:

		- Gross = 482,000.00
		- Exit fee = 2,410.00
		- WHT = 0.00
		- Net = 479,590.00
		"""
		result = calculate_redemption_pricing(
			units=Decimal("4000.000000"),
			bid_price=Decimal("120.500000"),
			exit_fee_pct=Decimal("0.5"),
			wht_rate=Decimal("15.0"),
			wht_basis=None,
		)
		self.assertEqual(result["units"], Decimal("4000.000000"))
		self.assertEqual(result["bid_price"], Decimal("120.500000"))
		self.assertEqual(result["gross"], Decimal("482000.00"))
		self.assertEqual(result["exit_fee"], Decimal("2410.00"))
		self.assertEqual(result["wht"], Decimal("0.00"))
		self.assertEqual(result["net"], Decimal("479590.00"))

	def test_05_redemption_by_amount_rounds_units_up(self):
		"""Redemption by amount: units = amount / bid rounded UP to 6 dp."""
		# 100,000 / 120.500000 = 829.875518672... -> rounds UP to 829.875519
		units = calculate_units_for_redemption_amount(
			requested_amount=Decimal("100000.00"),
			bid_price=Decimal("120.500000"),
		)
		self.assertEqual(units, Decimal("829.875519"))

	def test_06_redemption_wht_bases(self):
		"""Verify WHT calculation across None, Gross Proceeds, and Gain over Cost."""
		# 1. Gross Proceeds: 1,000 units @ 120.00 = 120,000.00, exit fee 0%, WHT 15% = 18,000.00
		res_gross = calculate_redemption_pricing(
			units=Decimal("1000"),
			bid_price=Decimal("120.000000"),
			exit_fee_pct=Decimal("0"),
			wht_rate=Decimal("15"),
			wht_basis="Gross Proceeds",
		)
		self.assertEqual(res_gross["gross"], Decimal("120000.00"))
		self.assertEqual(res_gross["wht"], Decimal("18000.00"))
		self.assertEqual(res_gross["net"], Decimal("102000.00"))

		# 2. Gain over Cost: 1,000 units @ 120.00 (cost 100.00) -> gain = 20,000.00, WHT 15% = 3,000.00
		res_gain = calculate_redemption_pricing(
			units=Decimal("1000"),
			bid_price=Decimal("120.000000"),
			exit_fee_pct=Decimal("0"),
			wht_rate=Decimal("15"),
			wht_basis="Gain over Cost",
			cost_per_unit=Decimal("100.000000"),
		)
		self.assertEqual(res_gain["gross"], Decimal("120000.00"))
		self.assertEqual(res_gain["wht"], Decimal("3000.00"))
		self.assertEqual(res_gain["net"], Decimal("117000.00"))
