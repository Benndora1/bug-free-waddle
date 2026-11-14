"""Unit ledger calculation and persistence service.

Follows AGENTS.md and .agents/rules/accounting.md:
- Pure Decimal arithmetic inside calculation logic
- Append-only immutable unit ledger (Asset Unit Ledger Entry)
- Cancellations insert negating entries with original marked is_cancelled=1
- No direct mutations of portfolio unit counters
"""

from decimal import Decimal
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, nowdate, nowtime


def get_unit_balance(investor: str, fund: str, as_of_date: str | Any = None) -> Decimal:
	"""Returns the net unit balance for an investor in a fund as of a specific date.

	Sums unit ledger entries up to as_of_date (cancelled entries are negated by their reversal entries).
	"""
	if not investor or not fund:
		return Decimal("0.000000")

	filters: dict[str, Any] = {
		"investor": investor,
		"fund": fund,
	}
	if as_of_date:
		filters["posting_date"] = ["<=", as_of_date]

	entries = frappe.get_all(
		"Asset Unit Ledger Entry",
		filters=filters,
		fields=["units"],
	)

	total = Decimal("0.0")
	for e in entries:
		total += Decimal(str(round(flt(e.units), 6)))

	return total.quantize(Decimal("0.000001"))


def get_fund_units_in_issue(fund: str, as_of_date: str | Any = None) -> Decimal:
	"""Returns the total units in issue for a fund as of a specific date.

	Sums unit ledger entries across all unitholders.
	"""
	if not fund:
		return Decimal("0.000000")

	filters: dict[str, Any] = {
		"fund": fund,
	}
	if as_of_date:
		filters["posting_date"] = ["<=", as_of_date]

	entries = frappe.get_all(
		"Asset Unit Ledger Entry",
		filters=filters,
		fields=["units"],
	)

	total = Decimal("0.0")
	for e in entries:
		total += Decimal(str(round(flt(e.units), 6)))

	return total.quantize(Decimal("0.000001"))


def make_unit_ledger_entry(voucher: Any, rows: list[dict[str, Any]]) -> list[str]:
	"""Inserts rows into Asset Unit Ledger Entry.

	Never edits existing rows or alters historical units.
	"""
	created_names: list[str] = []
	v_type = getattr(voucher, "doctype", None)
	v_name = getattr(voucher, "name", None)

	default_date = (
		getattr(voucher, "posting_date", None)
		or getattr(voucher, "subscription_date", None)
		or getattr(voucher, "redemption_date", None)
		or getattr(voucher, "switch_date", None)
		or nowdate()
	)

	for row in rows:
		entry = frappe.new_doc("Asset Unit Ledger Entry")
		entry.posting_date = row.get("posting_date") or default_date
		entry.posting_time = row.get("posting_time") or nowtime()
		entry.investor = row["investor"]
		entry.fund = row["fund"]
		entry.voucher_type = v_type or row.get("voucher_type")
		entry.voucher_no = v_name or row.get("voucher_no")
		entry.entry_type = row.get("entry_type", "Subscription")

		# Exact unit decimal precision 6
		unit_dec = Decimal(str(row.get("units", 0.0))).quantize(Decimal("0.000001"))
		entry.units = float(unit_dec)
		entry.price_per_unit = flt(row.get("price_per_unit", 0.0), 6)
		entry.amount = flt(row.get("amount", 0.0), 2)
		entry.currency = row.get("currency")
		entry.is_cancelled = 0
		entry.remarks = row.get("remarks")
		entry.flags.ignore_links = True

		entry.insert(ignore_permissions=True)
		created_names.append(entry.name)

	return created_names


def reverse_unit_ledger_entries(voucher_type: str, voucher_no: str) -> list[str]:
	"""Reverses unit ledger entries for a cancelled voucher.

	Marks original entries is_cancelled=1 and inserts exact negating entries.
	Never deletes rows.
	"""
	originals = frappe.get_all(
		"Asset Unit Ledger Entry",
		filters={
			"voucher_type": voucher_type,
			"voucher_no": voucher_no,
			"is_cancelled": 0,
		},
		fields=[
			"name",
			"posting_date",
			"posting_time",
			"investor",
			"fund",
			"voucher_type",
			"voucher_no",
			"entry_type",
			"units",
			"price_per_unit",
			"amount",
			"currency",
		],
	)

	reversal_names: list[str] = []
	for orig in originals:
		# 1. Mark original row is_cancelled=1
		frappe.db.set_value("Asset Unit Ledger Entry", orig.name, "is_cancelled", 1)

		# 2. Insert negating reversal row
		rev = frappe.new_doc("Asset Unit Ledger Entry")
		rev.posting_date = orig.posting_date
		rev.posting_time = nowtime()
		rev.investor = orig.investor
		rev.fund = orig.fund
		rev.voucher_type = orig.voucher_type
		rev.voucher_no = orig.voucher_no
		rev.entry_type = orig.entry_type

		# Negating units and amount
		rev.units = -flt(orig.units, 6)
		rev.price_per_unit = orig.price_per_unit
		rev.amount = -flt(orig.amount, 2) if orig.amount else 0.0
		rev.currency = orig.currency
		rev.is_cancelled = 0
		rev.remarks = _("Reversal of {0}").format(orig.name)
		rev.flags.ignore_links = True

		rev.insert(ignore_permissions=True)
		reversal_names.append(rev.name)

	return reversal_names


def rebuild_portfolio(investor: str, fund: str) -> None:
	"""Rebuilds Asset Investor Portfolio counters and status purely from Asset Unit Ledger Entry.

	Ensures portfolio total_units, total_invested_amount, and total_withdrawn_amount
	match the immutable ledger sum exactly.
	"""
	if not investor or not fund:
		return

	portfolio_id = f"{investor}-{fund}"
	entries = frappe.get_all(
		"Asset Unit Ledger Entry",
		filters={
			"investor": investor,
			"fund": fund,
		},
		fields=["units", "amount", "price_per_unit", "posting_date", "entry_type"],
		order_by="posting_date asc, creation asc",
	)

	total_units = Decimal("0.0")
	total_invested = Decimal("0.0")
	total_withdrawn = Decimal("0.0")
	last_tx_date = None
	first_sub_date = None

	for e in entries:
		u = Decimal(str(round(flt(e.units), 6)))
		amt = Decimal(str(round(flt(e.amount or 0.0), 2)))
		total_units += u

		if e.entry_type in ("Subscription", "Switch In", "Distribution Reinvestment", "Transfer In"):
			total_invested += amt
			if not first_sub_date and u > Decimal("0.0"):
				first_sub_date = e.posting_date
		elif e.entry_type in ("Redemption", "Switch Out", "Transfer Out"):
			total_withdrawn += amt

		last_tx_date = e.posting_date

	if not frappe.db.exists("Asset Investor Portfolio", portfolio_id):
		port = frappe.new_doc("Asset Investor Portfolio")
		port.name = portfolio_id
		port.investor = investor
		port.fund = fund
		fund_doc = frappe.get_doc("Asset Fund", fund)
		port.currency = fund_doc.currency
		port.first_subscription_date = first_sub_date or nowdate()
	else:
		port = frappe.get_doc("Asset Investor Portfolio", portfolio_id)
		fund_doc = frappe.get_doc("Asset Fund", fund)

	port.total_units = float(total_units.quantize(Decimal("0.0001")))
	port.total_invested_amount = float(total_invested.quantize(Decimal("0.01")))
	port.total_withdrawn_amount = float(total_withdrawn.quantize(Decimal("0.01")))
	if last_tx_date:
		port.last_transaction_date = last_tx_date

	# Re-value portfolio using current fund NAV
	nav = fund_doc.current_nav_per_unit or 100.0
	port.recalculate_valuation(nav)
	port.portfolio_status = "Active" if port.total_units > 0 else "Closed"
	port.save(ignore_permissions=True)

	# Keep fund's total_units_in_issue reconciled to the ledger
	fund_units = get_fund_units_in_issue(fund)
	frappe.db.set_value("Asset Fund", fund, "total_units_in_issue", float(fund_units))
