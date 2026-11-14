from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import getdate

from asset_management.services.units import get_fund_units_in_issue


def calculate_reconciliation_metrics(
	units_in_issue: Decimal | float | int,
	nav_per_unit: Decimal | float | int,
	gl_total_assets: Decimal | float | int,
	gl_total_liabilities: Decimal | float | int,
	tolerance: Decimal | float | int = Decimal("0.05"),
) -> dict[str, Decimal | bool]:
	"""Pure calculation of unit-register value vs GL net assets and tolerance check."""
	units = Decimal(str(units_in_issue or "0.000000")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
	nav = Decimal(str(nav_per_unit or "0.000000")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
	assets = Decimal(str(gl_total_assets or "0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	liabilities = Decimal(str(gl_total_liabilities or "0.00")).quantize(
		Decimal("0.01"), rounding=ROUND_HALF_UP
	)
	tol = abs(Decimal(str(tolerance if tolerance is not None else "0.05"))).quantize(
		Decimal("0.01"), rounding=ROUND_HALF_UP
	)

	register_value = (units * nav).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	gl_net_assets = (assets - liabilities).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	difference = (register_value - gl_net_assets).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	within_tolerance = abs(difference) <= tol

	return {
		"units_in_issue": units,
		"nav_per_unit": nav,
		"register_value": register_value,
		"gl_total_assets": assets,
		"gl_total_liabilities": liabilities,
		"gl_net_assets": gl_net_assets,
		"difference": difference,
		"tolerance": tol,
		"within_tolerance": within_tolerance,
	}


def get_company_gl_assets_and_liabilities(
	company: str,
	as_of_date: str,
	exclude_voucher: tuple[str, str] | None = None,
) -> tuple[Decimal, Decimal]:
	"""Returns (total_assets, total_liabilities) for `company` as at `as_of_date` from non-cancelled GL Entries."""
	if not company or not frappe.db.exists("Company", company):
		return Decimal("0.00"), Decimal("0.00")

	gle = frappe.qb.DocType("GL Entry")
	acc = frappe.qb.DocType("Account")

	query = (
		frappe.qb.from_(gle)
		.inner_join(acc)
		.on(gle.account == acc.name)
		.select(
			acc.root_type,
			Coalesce(Sum(gle.debit), 0).as_("total_debit"),
			Coalesce(Sum(gle.credit), 0).as_("total_credit"),
		)
		.where(
			(gle.company == company)
			& (gle.is_cancelled == 0)
			& (gle.posting_date <= getdate(as_of_date))
			& (acc.root_type.isin(["Asset", "Liability"]))
		)
		.groupby(acc.root_type)
	)

	if exclude_voucher:
		v_type, v_no = exclude_voucher
		query = query.where(~((gle.voucher_type == v_type) & (gle.voucher_no == v_no)))

	rows = query.run(as_dict=True)

	total_assets = Decimal("0.00")
	total_liabilities = Decimal("0.00")
	for row in rows:
		dr = Decimal(str(row.get("total_debit") or "0.00"))
		cr = Decimal(str(row.get("total_credit") or "0.00"))
		if row.get("root_type") == "Asset":
			total_assets += dr - cr
		elif row.get("root_type") == "Liability":
			total_liabilities += cr - dr

	return (
		total_assets.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
		total_liabilities.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
	)


def get_reconciliation_tolerance() -> Decimal:
	"""Reads reconciliation tolerance from Fund Management Settings (defaults to 0.05)."""
	if frappe.db.exists("DocType", "Fund Management Settings"):
		settings = frappe.get_single("Fund Management Settings")
		tol = getattr(settings, "reconciliation_tolerance", None)
		if tol is None or tol == "":
			tol = getattr(settings, "max_rounding_tolerance", None)
		if tol is not None and tol != "":
			return Decimal(str(tol)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	return Decimal("0.05")


def get_published_nav_per_unit(fund: str, target_date: str) -> Decimal:
	"""Reads nav_per_unit for (fund, target_date) from Asset Fund Price (or approved Valuation)."""
	target_dt = getdate(target_date)
	if frappe.db.exists("DocType", "Asset Fund Price"):
		price = frappe.db.get_value(
			"Asset Fund Price",
			{"fund": fund, "price_date": target_dt},
			"nav_per_unit",
		)
		if price is not None:
			return Decimal(str(price)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

	val_nav = frappe.db.get_value(
		"Asset Fund Valuation",
		{"fund": fund, "valuation_date": target_dt, "status": "Approved"},
		"nav_per_unit",
	)
	if val_nav is not None:
		return Decimal(str(val_nav)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

	return Decimal("0.000000")


def reconcile_fund(fund: str, date: str) -> dict[str, Any]:
	"""Reconciles a fund's unit register against its company's GL net assets as of `date`.

	Returns dict with:
	- units_in_issue (Decimal, 6 dp, from Asset Unit Ledger Entry)
	- nav_per_unit (Decimal, 6 dp, from Asset Fund Price)
	- register_value (Decimal, 2 dp, units x nav)
	- gl_net_assets (Decimal, 2 dp, total assets minus total liabilities from GL)
	- difference (Decimal, 2 dp, register_value - gl_net_assets)
	- within_tolerance (bool)
	"""
	if not fund or not frappe.db.exists("Asset Fund", fund):
		frappe.throw(_("Asset Fund {0} not found.").format(fund), title=_("Fund Not Found"))

	target_date = str(getdate(date))
	fund_doc = frappe.get_doc("Asset Fund", fund)

	units_in_issue = get_fund_units_in_issue(fund, target_date)
	nav_per_unit = get_published_nav_per_unit(fund, target_date)
	total_assets, total_liabilities = get_company_gl_assets_and_liabilities(fund_doc.company, target_date)
	tolerance = get_reconciliation_tolerance()

	metrics = calculate_reconciliation_metrics(
		units_in_issue=units_in_issue,
		nav_per_unit=nav_per_unit,
		gl_total_assets=total_assets,
		gl_total_liabilities=total_liabilities,
		tolerance=tolerance,
	)

	return {
		"fund": fund,
		"date": target_date,
		"units_in_issue": metrics["units_in_issue"],
		"nav_per_unit": metrics["nav_per_unit"],
		"register_value": metrics["register_value"],
		"gl_net_assets": metrics["gl_net_assets"],
		"difference": metrics["difference"],
		"within_tolerance": metrics["within_tolerance"],
		"tolerance": metrics["tolerance"],
	}
