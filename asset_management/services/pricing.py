"""Pricing service for fund subscriptions, redemptions, and forward pricing (services/pricing.py).

Pure calculation functions use decimal.Decimal with exact rounding rules:
- Units and prices: 6 decimal places (ROUND_DOWN for allotted units)
- Currency amounts: 2 decimal places (ROUND_HALF_UP)
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Any

import frappe
from frappe.utils import add_days, get_time, getdate


def calculate_subscription_pricing(
	gross_amount: Decimal | float | int,
	fee_rate_pct: Decimal | float | int,
	offer_price: Decimal | float | int,
) -> dict[str, Decimal]:
	"""Pure calculation of subscription entry fee, net capital, and allocated units.

	- entry_fee = gross * fee_rate_pct / 100 (rounded to 2 dp)
	- net_amount = gross - entry_fee
	- units = net_amount / offer_price (rounded down to 6 dp)
	- residual_cash = net_amount - (units * offer_price) remaining as client cash
	"""
	gross = Decimal(str(gross_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	fee_rate = Decimal(str(fee_rate_pct))
	offer = Decimal(str(offer_price)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

	if offer <= Decimal("0.000000"):
		raise ValueError("Offer price must be greater than zero.")

	entry_fee = (gross * (fee_rate / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	net_amount = (gross - entry_fee).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

	# Units allotted rounded down to 6 decimal places per ADR-0004 & accounting rules
	units = (net_amount / offer).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)

	invested_cash = (units * offer).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	if invested_cash > net_amount:
		invested_cash = net_amount

	residual_cash = (net_amount - invested_cash).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	if residual_cash < Decimal("0.00"):
		residual_cash = Decimal("0.00")

	return {
		"gross_amount": gross,
		"entry_fee": entry_fee,
		"net_amount": net_amount,
		"units": units,
		"invested_cash": invested_cash,
		"residual_cash": residual_cash,
		"offer_price": offer,
	}


def get_applicable_fund_price(
	fund: str,
	dealing_date: str,
	dealing_time: str | None = None,
) -> Decimal | None:
	"""Returns the first published offer price on or after the dealing cut-off (ADR-0004).

	Returns None if no price has been published yet for the dealing date/time,
	which puts the transaction in 'Pending Price' status.
	"""
	if not fund or not frappe.db.exists("Asset Fund", fund):
		return None

	fund_doc = frappe.get_doc("Asset Fund", fund)
	effective_date = getdate(dealing_date)

	cut_off_str = getattr(fund_doc, "dealing_cut_off_time", None) or "15:00:00"
	if dealing_time:
		try:
			cut_off = get_time(str(cut_off_str))
			trade_time = get_time(str(dealing_time))
			if trade_time > cut_off:
				# Post cut-off dealings roll forward to the next valuation date
				effective_date = getdate(add_days(dealing_date, 1))
		except Exception:
			pass

	# 1. Check for published Asset Fund Valuation on or after effective_date
	valuations = frappe.get_all(
		"Asset Fund Valuation",
		filters={
			"fund": fund,
			"valuation_date": [">=", effective_date],
			"status": "Approved",
		},
		fields=["offer_price", "nav_per_unit", "valuation_date"],
		order_by="valuation_date asc",
		limit=1,
	)

	if valuations:
		val = valuations[0]
		price = val.offer_price or val.nav_per_unit
		if price and price > 0:
			return Decimal(str(price)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

	# 2. Check Asset Fund's published current prices if valuation date is on/after effective_date
	if fund_doc.last_valuation_date:
		last_val_date = getdate(fund_doc.last_valuation_date)
		if last_val_date >= effective_date:
			price = (
				fund_doc.current_offer_price
				or fund_doc.current_nav_per_unit
				or getattr(fund_doc, "offer_price", None)
			)
			if price and price > 0:
				return Decimal(str(price)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

	return None
