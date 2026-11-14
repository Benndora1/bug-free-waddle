"""Tests for pricing calculations and fund price resolution (services/pricing.py)."""

import unittest
from decimal import Decimal

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import add_days, nowdate

from asset_management.services.pricing import (
	calculate_subscription_pricing,
	get_applicable_fund_price,
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
