"""Patch: convert existing Asset Investor Register Line rows into Asset Unit Ledger Entry rows and rebuild portfolios."""

import frappe

from asset_management.services.units import rebuild_portfolio


def execute():
	frappe.reload_doc("asset_management", "doctype", "asset_unit_ledger_entry")

	if not frappe.db.table_exists("Asset Unit Ledger Entry"):
		return

	# Add composite index on (fund, investor, posting_date)
	try:
		frappe.db.add_index(
			"Asset Unit Ledger Entry", ["fund", "investor", "posting_date"], "idx_fund_investor_date"
		)
	except Exception:
		pass

	if not frappe.db.table_exists("Asset Investor Register Line"):
		return

	# Fetch existing register lines
	reg_lines = frappe.get_all(
		"Asset Investor Register Line",
		fields=[
			"posting_date",
			"investor",
			"fund",
			"entry_type",
			"voucher_type",
			"voucher_no",
			"units",
			"nav_per_unit",
			"gross_amount",
			"net_amount",
		],
		order_by="posting_date asc, creation asc",
	)

	pairs_to_rebuild = set()

	for reg in reg_lines:
		# Skip invalid or orphaned test lines where investor or fund no longer exist
		if not frappe.db.exists("Asset Investor", reg.investor) or not frappe.db.exists(
			"Asset Fund", reg.fund
		):
			continue

		# Check if already migrated
		exists = frappe.db.exists(
			"Asset Unit Ledger Entry",
			{
				"voucher_type": reg.voucher_type,
				"voucher_no": reg.voucher_no,
				"fund": reg.fund,
				"investor": reg.investor,
			},
		)
		if not exists:
			entry = frappe.new_doc("Asset Unit Ledger Entry")
			entry.posting_date = reg.posting_date
			entry.investor = reg.investor
			entry.fund = reg.fund
			entry.voucher_type = reg.voucher_type
			entry.voucher_no = reg.voucher_no
			entry.entry_type = reg.entry_type
			entry.units = reg.units
			entry.price_per_unit = reg.nav_per_unit
			entry.amount = abs(reg.gross_amount or reg.net_amount or 0.0)
			entry.is_cancelled = 0
			entry.flags.ignore_links = True
			entry.insert(ignore_permissions=True)

		pairs_to_rebuild.add((reg.investor, reg.fund))

	# Rebuild portfolio balances
	for inv, fnd in pairs_to_rebuild:
		try:
			rebuild_portfolio(inv, fnd)
		except Exception as e:
			frappe.log_error(f"Failed to rebuild portfolio for {inv}-{fnd}: {e}")
