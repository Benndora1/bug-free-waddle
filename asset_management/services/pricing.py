"""Pricing service for fund subscriptions, redemptions, and forward pricing (services/pricing.py).

Pure calculation functions use decimal.Decimal with exact rounding rules:
- Units and prices: 6 decimal places (ROUND_DOWN for allotted units, ROUND_UP for redemption by amount)
- Currency amounts: 2 decimal places (ROUND_HALF_UP)
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal
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


def calculate_units_for_redemption_amount(
	requested_amount: Decimal | float | int,
	bid_price: Decimal | float | int,
) -> Decimal:
	"""Calculates units to redeem for a requested currency amount:

	units = amount / bid_price rounded UP to 6 decimal places.
	"""
	amount = Decimal(str(requested_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	bid = Decimal(str(bid_price)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

	if bid <= Decimal("0.000000"):
		raise ValueError("Bid price must be greater than zero.")

	return (amount / bid).quantize(Decimal("0.000001"), rounding=ROUND_UP)


def calculate_redemption_pricing(
	units: Decimal | float | int,
	bid_price: Decimal | float | int,
	exit_fee_pct: Decimal | float | int = Decimal("0.0"),
	wht_rate: Decimal | float | int = Decimal("0.0"),
	wht_basis: str | None = None,
	cost_per_unit: Decimal | float | int = Decimal("0.0"),
) -> dict[str, Decimal]:
	"""Pure calculation of redemption gross proceeds, exit fee, WHT, and net payout:

	- gross = units x bid_price (2 dp)
	- exit_fee = gross x exit_fee_pct / 100 (2 dp)
	- wht by basis (None | Gross Proceeds | Gain over Cost; default None)
	- net = gross - exit_fee - wht
	"""
	u = Decimal(str(units)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
	bid = Decimal(str(bid_price)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

	if bid <= Decimal("0.000000"):
		raise ValueError("Bid price must be greater than zero.")

	gross = (u * bid).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	fee_pct = Decimal(str(exit_fee_pct or "0.0"))
	exit_fee = (gross * (fee_pct / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

	tax_pct = Decimal(str(wht_rate or "0.0"))
	basis = (wht_basis or "None").strip()

	if basis == "Gross Proceeds" and tax_pct > Decimal("0.0"):
		taxable_base = gross - exit_fee
		if taxable_base < Decimal("0.00"):
			taxable_base = Decimal("0.00")
		wht = (taxable_base * (tax_pct / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	elif basis == "Gain over Cost" and tax_pct > Decimal("0.0"):
		cost_unit = Decimal(str(cost_per_unit or "0.0")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
		total_cost = (u * cost_unit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
		gain = gross - exit_fee - total_cost
		if gain < Decimal("0.00"):
			gain = Decimal("0.00")
		wht = (gain * (tax_pct / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	else:
		wht = Decimal("0.00")

	net = (gross - exit_fee - wht).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

	return {
		"units": u,
		"bid_price": bid,
		"gross": gross,
		"exit_fee": exit_fee,
		"wht": wht,
		"net": net,
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

	# 1. Check Asset Fund Price history table on or after effective_date (R-11)
	if frappe.db.exists("DocType", "Asset Fund Price"):
		fund_prices = frappe.get_all(
			"Asset Fund Price",
			filters={
				"fund": fund,
				"price_date": [">=", effective_date],
			},
			fields=["offer_price", "nav_per_unit", "price_date"],
			order_by="price_date asc",
			limit=1,
		)
		if fund_prices:
			fp = fund_prices[0]
			price = fp.offer_price or fp.nav_per_unit
			if price and price > 0:
				return Decimal(str(price)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

	# 2. Check for published Asset Fund Valuation on or after effective_date
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

	# 3. Check Asset Fund's published current prices if valuation date is on/after effective_date
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


def get_applicable_bid_price(
	fund: str,
	dealing_date: str,
	dealing_time: str | None = None,
) -> Decimal | None:
	"""Returns the first published bid price on or after the dealing cut-off (ADR-0004).

	Returns None if no price has been published yet for the dealing date/time,
	which puts the redemption/switch in 'Pending Price' status.
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
				effective_date = getdate(add_days(dealing_date, 1))
		except Exception:
			pass

	# 1. Check Asset Fund Price history table on or after effective_date (R-11)
	if frappe.db.exists("DocType", "Asset Fund Price"):
		fund_prices = frappe.get_all(
			"Asset Fund Price",
			filters={
				"fund": fund,
				"price_date": [">=", effective_date],
			},
			fields=["bid_price", "nav_per_unit", "price_date"],
			order_by="price_date asc",
			limit=1,
		)
		if fund_prices:
			fp = fund_prices[0]
			price = fp.bid_price or fp.nav_per_unit
			if price and price > 0:
				return Decimal(str(price)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

	# 2. Check for published Asset Fund Valuation on or after effective_date
	valuations = frappe.get_all(
		"Asset Fund Valuation",
		filters={
			"fund": fund,
			"valuation_date": [">=", effective_date],
			"status": "Approved",
		},
		fields=["bid_price", "nav_per_unit", "valuation_date"],
		order_by="valuation_date asc",
		limit=1,
	)

	if valuations:
		val = valuations[0]
		price = val.bid_price or val.nav_per_unit
		if price and price > 0:
			return Decimal(str(price)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

	# 3. Check Asset Fund's published current prices if valuation date is on/after effective_date
	if fund_doc.last_valuation_date:
		last_val_date = getdate(fund_doc.last_valuation_date)
		if last_val_date >= effective_date:
			price = (
				fund_doc.current_bid_price
				or fund_doc.current_nav_per_unit
				or getattr(fund_doc, "bid_price", None)
			)
			if price and price > 0:
				return Decimal(str(price)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

	return None


def get_security_price_for_valuation(
	security: str,
	valuation_date: str,
) -> tuple[Decimal | None, str | None, bool]:
	"""Looks up Asset Security Price for `security` on `valuation_date`.

	If missing on `valuation_date` and Fund Management Settings enables
	`allow_stale_security_prices` with `max_stale_price_days > 0`, returns the most
	recent price within `[valuation_date - max_stale_price_days, valuation_date)`
	with `is_stale = True`.
	Never falls back to 100.0.
	"""
	if not security or not frappe.db.exists("DocType", "Asset Security Price"):
		return None, None, False

	val_dt = getdate(valuation_date)
	exact = frappe.get_all(
		"Asset Security Price",
		filters={"security": security, "price_date": val_dt},
		fields=["clean_price", "price_date"],
		limit=1,
	)
	if exact and exact[0].clean_price and exact[0].clean_price > 0:
		return (
			Decimal(str(exact[0].clean_price)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
			str(exact[0].price_date),
			False,
		)

	# Check stale price allowance in Fund Management Settings
	allow_stale = False
	max_days = 0
	if frappe.db.exists("DocType", "Fund Management Settings"):
		settings = frappe.get_single("Fund Management Settings")
		allow_stale = bool(getattr(settings, "allow_stale_security_prices", 0))
		max_days = int(getattr(settings, "max_stale_price_days", 0) or 0)

	if allow_stale and max_days > 0:
		earliest_dt = getdate(add_days(val_dt, -max_days))
		stale_rows = frappe.get_all(
			"Asset Security Price",
			filters={
				"security": security,
				"price_date": ["between", [earliest_dt, val_dt]],
			},
			fields=["clean_price", "price_date"],
			order_by="price_date desc",
			limit=1,
		)
		if stale_rows and stale_rows[0].clean_price and stale_rows[0].clean_price > 0:
			return (
				Decimal(str(stale_rows[0].clean_price)).quantize(
					Decimal("0.000001"), rounding=ROUND_HALF_UP
				),
				str(stale_rows[0].price_date),
				True,
			)

	return None, None, False
