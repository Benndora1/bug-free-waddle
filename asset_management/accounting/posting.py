"""Posting adapter for fund accounting general ledger entries (accounting/posting.py).

Per ADR-0003 and accounting rules:
ALL GL postings across the system go through this module, wrapping ERPNext make_gl_entries.
No other module may create GL Entries or Journal Entries for business events.
"""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


def get_accounting_settings() -> Any:
	"""Returns the single Fund Management Settings document or empty mock if not initialized."""
	if frappe.db.exists("DocType", "Fund Management Settings"):
		return frappe.get_single("Fund Management Settings")
	return None


def get_default_cost_center(company: str) -> str | None:
	"""Returns the default leaf cost center for the company."""
	cc = frappe.get_cached_value("Company", company, "cost_center")
	if not cc:
		ccs = frappe.get_all(
			"Cost Center", filters={"company": company, "is_group": 0}, pluck="name", limit=1
		)
		if ccs:
			cc = ccs[0]
	return cc


def post_gl(doc: Document, gl_map: list[dict[str, Any]]) -> None:
	"""Validates and posts general ledger entries for a transaction document.

	Wraps erpnext.accounts.general_ledger.make_gl_entries.
	1. Validates that gl_map balances to 0 in company currency for each company.
	2. Automatically posts any difference within max_rounding_tolerance to the Rounding Account.
	3. Rejects entries if the difference exceeds the rounding tolerance.
	"""
	if not gl_map:
		return

	settings = get_accounting_settings()
	max_tolerance = Decimal(str(getattr(settings, "max_rounding_tolerance", None) or "0.05"))

	# Group entries by company to validate each company's balance independently
	entries_by_company = defaultdict(list)
	for entry in gl_map:
		comp = entry.get("company")
		if not comp:
			comp = (
				getattr(doc, "company", None)
				or getattr(settings, "default_fund_company", None)
				or getattr(settings, "fund_manager_company", None)
			)
			entry["company"] = comp
		entries_by_company[comp].append(entry)

	adjusted_gl_map: list[dict[str, Any]] = []

	for company, entries in entries_by_company.items():
		total_debit = Decimal("0.00")
		total_credit = Decimal("0.00")

		for e in entries:
			# Ensure base document linkage
			if not e.get("voucher_type"):
				e["voucher_type"] = doc.doctype
			if not e.get("voucher_no"):
				e["voucher_no"] = doc.name
			if not e.get("posting_date"):
				e["posting_date"] = (
					getattr(doc, "posting_date", None) or getattr(doc, "subscription_date", None) or nowdate()
				)
			if not e.get("cost_center"):
				e["cost_center"] = get_default_cost_center(company)

			# Harmonize debit and credit values
			deb = Decimal(str(e.get("debit", 0) or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
			cred = Decimal(str(e.get("credit", 0) or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
			e["debit"] = float(deb)
			e["credit"] = float(cred)
			e["debit_in_account_currency"] = float(e.get("debit_in_account_currency") or deb)
			e["credit_in_account_currency"] = float(e.get("credit_in_account_currency") or cred)

			total_debit += deb
			total_credit += cred

		diff = (total_debit - total_credit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

		if diff != Decimal("0.00"):
			if abs(diff) <= max_tolerance:
				rounding_acc = getattr(settings, "rounding_account", None) or frappe.db.get_value(
					"Company", company, "round_off_account"
				)
				if not rounding_acc:
					frappe.throw(
						_(
							"GL map for company {0} has a rounding difference of {1}, but no Rounding Account is configured."
						).format(company, diff),
						title=_("Missing Rounding Account"),
					)

				# Balance difference to Rounding Account
				rounding_entry: dict[str, Any] = {
					"company": company,
					"account": rounding_acc,
					"cost_center": get_default_cost_center(company),
					"voucher_type": doc.doctype,
					"voucher_no": doc.name,
					"posting_date": entries[0].get("posting_date") or nowdate(),
					"against": _("Rounding Adjustment"),
					"remarks": _("Automatic rounding difference adjustment"),
				}

				if diff > 0:
					# More debit than credit -> credit rounding
					rounding_entry["debit"] = 0.0
					rounding_entry["credit"] = float(diff)
					rounding_entry["debit_in_account_currency"] = 0.0
					rounding_entry["credit_in_account_currency"] = float(diff)
				else:
					# More credit than debit -> debit rounding
					rounding_entry["debit"] = float(abs(diff))
					rounding_entry["credit"] = 0.0
					rounding_entry["debit_in_account_currency"] = float(abs(diff))
					rounding_entry["credit_in_account_currency"] = 0.0

				entries.append(rounding_entry)
			else:
				frappe.throw(
					_(
						"GL map for company {0} is out of balance. Total Debit: {1}, Total Credit: {2}, Difference: {3} (exceeds tolerance {4})."
					).format(company, total_debit, total_credit, diff, max_tolerance),
					title=_("GL Imbalance Error"),
				)

		adjusted_gl_map.extend([frappe._dict(e) for e in entries])

	from erpnext.accounts.general_ledger import make_gl_entries

	make_gl_entries(adjusted_gl_map, cancel=False)


def reverse_gl(doc: Document) -> None:
	"""Reverses all active General Ledger entries previously posted for this document.

	Wraps erpnext.accounts.general_ledger.make_gl_entries(..., cancel=True).
	"""
	from erpnext.accounts.general_ledger import make_gl_entries

	existing_entries = frappe.get_all(
		"GL Entry",
		filters={
			"voucher_type": doc.doctype,
			"voucher_no": doc.name,
			"is_cancelled": 0,
		},
		fields=["*"],
	)

	if not existing_entries:
		return

	entries = [frappe._dict(e) for e in existing_entries]
	make_gl_entries(entries, cancel=True)
