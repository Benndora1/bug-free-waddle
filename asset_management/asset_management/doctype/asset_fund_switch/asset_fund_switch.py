from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from asset_management.accounting.posting import get_accounting_settings, post_gl, reverse_gl
from asset_management.services.pricing import (
	calculate_redemption_pricing,
	calculate_subscription_pricing,
	calculate_units_for_redemption_amount,
	get_applicable_bid_price,
	get_applicable_fund_price,
)
from asset_management.services.units import (
	get_active_lien_units,
	get_unit_balance,
	make_unit_ledger_entry,
	rebuild_portfolio,
	reverse_unit_ledger_entries,
)


class AssetFundSwitch(Document):
	def validate(self):
		if not self.switch_date:
			self.switch_date = nowdate()

		if not self.maker:
			self.maker = getattr(self, "owner", None) or frappe.session.user

		if self.from_fund == self.to_fund:
			frappe.throw(_("Source Fund and Target Fund cannot be the same."))

		inv = frappe.get_doc("Asset Investor", self.investor)
		self.investor_name = inv.investor_name
		if inv.status != "Active":
			frappe.throw(
				_(
					"Investor {0} is currently {1}. Switches can only be processed for Active investors."
				).format(self.investor, inv.status)
			)

		from_fund = frappe.get_doc("Asset Fund", self.from_fund)

		total_units = get_unit_balance(self.investor, self.from_fund, self.switch_date)
		lien_units = get_active_lien_units(self.investor, self.from_fund, self.switch_date)
		free_units = total_units - lien_units

		if free_units <= Decimal("0.000000"):
			frappe.throw(
				_(
					"Insufficient free units. Investor {0} holds {1} units ({2} encumbered) in source fund {3} as of {4}."
				).format(self.investor, total_units, lien_units, from_fund.fund_name, self.switch_date)
			)

		req_units = Decimal("0.000000")
		if self.switch_by == "Units":
			if not self.switch_units or flt(self.switch_units, 6) <= 0:
				frappe.throw(_("Switch units must be greater than zero."))
			req_units = Decimal(str(self.switch_units)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
			if req_units > free_units:
				frappe.throw(
					_(
						"Insufficient free units. Requested switch units ({0}) exceed available free units ({1}) in source fund as of {2}."
					).format(req_units, free_units, self.switch_date)
				)

		# Forward pricing: Out leg at Fund A bid, In leg at Fund B offer for same dealing date
		received_at = getattr(self, "received_at", None)
		bid_a = get_applicable_bid_price(self.from_fund, self.switch_date, received_at)
		offer_b = get_applicable_fund_price(self.to_fund, self.switch_date, received_at)

		if not bid_a or bid_a <= Decimal("0.000000") or not offer_b or offer_b <= Decimal("0.000000"):
			self.status = "Pending Price"
			self.from_fund_bid_price = float(bid_a) if bid_a else 0.0
			self.to_fund_offer_price = float(offer_b) if offer_b else 0.0
			self.gross_switch_amount = 0.0
			self.switch_fee_amount = 0.0
			self.net_switch_amount = 0.0
			self.entry_fee_amount = 0.0
			self.units_allocated_to_fund = 0.0
			return

		self.from_fund_bid_price = float(bid_a)
		self.to_fund_offer_price = float(offer_b)

		if self.switch_by == "Units":
			u_out = req_units
		elif self.switch_by == "Amount":
			if not self.switch_amount or flt(self.switch_amount, 2) <= 0:
				frappe.throw(_("Please specify a valid switch amount."))
			u_out = calculate_units_for_redemption_amount(self.switch_amount, bid_a)
		elif self.switch_by == "Full Balance":
			u_out = free_units
		else:
			u_out = req_units

		if u_out <= Decimal("0.000000"):
			frappe.throw(_("Switch units must be greater than zero."))

		if u_out > free_units:
			frappe.throw(
				_(
					"Insufficient free units. Requested switch units ({0}) exceed available free units ({1}) in source fund as of {2}."
				).format(u_out, free_units, self.switch_date)
			)

		self.switch_units = float(u_out)

		# Out leg calculation (Fund A)
		out_pricing = calculate_redemption_pricing(
			units=u_out,
			bid_price=bid_a,
			exit_fee_pct=self.switch_fee_pct or 0.0,
			wht_rate=0.0,
			wht_basis=None,
		)
		self.gross_switch_amount = float(out_pricing["gross"])
		self.switch_fee_amount = float(out_pricing["exit_fee"])
		self.net_switch_amount = float(out_pricing["net"])

		# In leg calculation (Fund B)
		in_pricing = calculate_subscription_pricing(
			gross_amount=out_pricing["net"],
			fee_rate_pct=getattr(self, "entry_fee_pct", 0.0) or 0.0,
			offer_price=offer_b,
		)
		self.entry_fee_amount = float(in_pricing["entry_fee"])
		self.units_allocated_to_fund = float(in_pricing["units"])

		if self.status == "Pending Price":
			self.status = "Draft"

	def before_submit(self):
		if (
			self.status == "Pending Price"
			or not self.from_fund_bid_price
			or flt(self.from_fund_bid_price, 6) <= 0
			or not self.to_fund_offer_price
			or flt(self.to_fund_offer_price, 6) <= 0
		):
			frappe.throw(
				_(
					"Fund Switch {0} is in 'Pending Price' status and cannot be submitted until both source bid price and target offer price are published for dealing date {1}."
				).format(self.name, self.switch_date),
				title=_("Pending Price"),
			)

		if not self.approved_by_checker:
			frappe.throw(
				_("Inter-Fund Switch requires Checker sign-off (approved_by_checker = 1) before submission.")
			)
		maker = self.maker or getattr(self, "owner", None) or frappe.session.user
		if self.checker and maker == self.checker:
			frappe.throw(
				_("Maker and Checker cannot be the same user for Fund Switch {0}.").format(self.name)
			)

	def get_gl_entries(self) -> list[dict]:
		"""Constructs General Ledger entries across both Fund A Company and Fund B Company:

		Fund A Company (Source):
		- Dr Unitholders' Capital A (gross_switch_amount)
		- Cr Exit Fee Payable A (switch_fee_amount, if > 0)
		- Cr Due to Other Funds A (net_switch_amount)

		Fund B Company (Target):
		- Dr Due from Other Funds B (net_switch_amount)
		- Cr Entry Fee Payable B (entry_fee_amount, if > 0)
		- Cr Unitholders' Capital B (net_switch_amount - entry_fee_amount)
		"""
		settings = get_accounting_settings()
		fund_a = frappe.get_doc("Asset Fund", self.from_fund)
		fund_b = frappe.get_doc("Asset Fund", self.to_fund)

		comp_a = (
			getattr(fund_a, "company", None)
			or getattr(settings, "default_fund_company", None)
			or getattr(settings, "fund_manager_company", None)
		)
		comp_b = (
			getattr(fund_b, "company", None)
			or getattr(settings, "default_fund_company", None)
			or getattr(settings, "fund_manager_company", None)
		)

		cap_a = getattr(fund_a, "unitholders_capital_account", None)
		exit_fee_a = getattr(fund_a, "exit_fee_payable_account", None)
		due_to_a = getattr(fund_a, "due_to_other_funds_account", None)

		due_from_b = getattr(fund_b, "due_from_other_funds_account", None)
		entry_fee_b = getattr(fund_b, "entry_fee_payable_account", None)
		cap_b = getattr(fund_b, "unitholders_capital_account", None)

		gross_out = flt(self.gross_switch_amount, 2)
		fee_out = flt(self.switch_fee_amount, 2)
		net_moved = flt(self.net_switch_amount, 2)
		fee_in = flt(getattr(self, "entry_fee_amount", 0.0), 2)
		net_in_cap = round(net_moved - fee_in, 2)

		gl_entries: list[dict] = []

		# --- Fund A Company (Out Leg) ---
		gl_entries.append(
			{
				"company": comp_a,
				"account": cap_a,
				"debit": gross_out,
				"credit": 0.0,
				"against": due_to_a,
				"remarks": _("Switch Out of {0} units to {1} for investor {2}").format(
					self.switch_units, self.to_fund, self.investor
				),
				"posting_date": self.switch_date,
			}
		)
		if fee_out > 0:
			gl_entries.append(
				{
					"company": comp_a,
					"account": exit_fee_a,
					"debit": 0.0,
					"credit": fee_out,
					"against": cap_a,
					"remarks": _("Exit fee on switch {0}").format(self.name),
					"posting_date": self.switch_date,
				}
			)
		gl_entries.append(
			{
				"company": comp_a,
				"account": due_to_a,
				"debit": 0.0,
				"credit": net_moved,
				"against": cap_a,
				"remarks": _("Inter-fund payable to {0} on switch {1}").format(self.to_fund, self.name),
				"posting_date": self.switch_date,
			}
		)

		# --- Fund B Company (In Leg) ---
		gl_entries.append(
			{
				"company": comp_b,
				"account": due_from_b,
				"debit": net_moved,
				"credit": 0.0,
				"against": cap_b,
				"remarks": _("Inter-fund receivable from {0} on switch {1}").format(
					self.from_fund, self.name
				),
				"posting_date": self.switch_date,
			}
		)
		if fee_in > 0:
			gl_entries.append(
				{
					"company": comp_b,
					"account": entry_fee_b,
					"debit": 0.0,
					"credit": fee_in,
					"against": due_from_b,
					"remarks": _("Entry fee on switch {0}").format(self.name),
					"posting_date": self.switch_date,
				}
			)
		gl_entries.append(
			{
				"company": comp_b,
				"account": cap_b,
				"debit": 0.0,
				"credit": net_in_cap,
				"against": due_from_b,
				"remarks": _("Switch In of {0} units from {1} for investor {2}").format(
					self.units_allocated_to_fund, self.from_fund, self.investor
				),
				"posting_date": self.switch_date,
			}
		)

		return gl_entries

	def on_submit(self):
		"""Posts GL entries in both fund companies, records Switch Out & Switch In in unit ledger, and rebuilds portfolios."""
		# 1. Post to General Ledger in both Fund A and Fund B companies
		post_gl(self, self.get_gl_entries())

		# 2. Post to Immutable Unit Ledger
		make_unit_ledger_entry(
			self,
			[
				{
					"investor": self.investor,
					"fund": self.from_fund,
					"entry_type": "Switch Out",
					"units": -flt(self.switch_units, 6),
					"price_per_unit": flt(self.from_fund_bid_price, 6),
					"amount": flt(self.gross_switch_amount, 2),
					"posting_date": self.switch_date,
				},
				{
					"investor": self.investor,
					"fund": self.to_fund,
					"entry_type": "Switch In",
					"units": flt(self.units_allocated_to_fund, 6),
					"price_per_unit": flt(self.to_fund_offer_price, 6),
					"amount": flt(self.net_switch_amount, 2),
					"posting_date": self.switch_date,
				},
			],
		)

		# 3. Rebuild both source and target portfolios
		rebuild_portfolio(self.investor, self.from_fund)
		rebuild_portfolio(self.investor, self.to_fund)

		self.db_set("status", "Submitted")

	def before_cancel(self):
		self.ignore_linked_doctypes = [
			"GL Entry",
			"Payment Ledger Entry",
			"Asset Unit Ledger Entry",
			"Asset Investor Register Line",
		]

	def on_cancel(self):
		"""Reverses switch in GL and unit ledger, and rebuilds source and target portfolios."""
		reverse_gl(self)
		reverse_unit_ledger_entries("Asset Fund Switch", self.name)
		rebuild_portfolio(self.investor, self.from_fund)
		rebuild_portfolio(self.investor, self.to_fund)
		self.db_set("status", "Cancelled")
