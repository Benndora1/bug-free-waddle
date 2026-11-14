import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from asset_management.services.units import (
	get_unit_balance,
	make_unit_ledger_entry,
	rebuild_portfolio,
	reverse_unit_ledger_entries,
)


class AssetFundSwitch(Document):
	def validate(self):
		if not self.switch_date:
			self.switch_date = nowdate()

		if self.from_fund == self.to_fund:
			frappe.throw(_("Source Fund and Target Fund cannot be the same."))

		inv = frappe.get_doc("Asset Investor", self.investor)
		self.investor_name = inv.investor_name

		from_fund = frappe.get_doc("Asset Fund", self.from_fund)
		to_fund = frappe.get_doc("Asset Fund", self.to_fund)

		available_units = float(get_unit_balance(self.investor, self.from_fund, self.switch_date))
		if available_units <= 0:
			frappe.throw(
				_("Insufficient units. Investor {0} holds 0.0 units in source fund {1} as of {2}.").format(
					self.investor, from_fund.fund_name, self.switch_date
				)
			)

		if not self.from_fund_bid_price or self.from_fund_bid_price <= 0:
			self.from_fund_bid_price = from_fund.current_bid_price or from_fund.current_nav_per_unit or 100.0

		if not self.to_fund_offer_price or self.to_fund_offer_price <= 0:
			self.to_fund_offer_price = to_fund.current_offer_price or to_fund.current_nav_per_unit or 100.0

		if self.switch_by == "Units":
			self.switch_units = round(flt(self.switch_units), 4)
		elif self.switch_by == "Amount":
			self.switch_units = round(flt(self.switch_amount) / flt(self.from_fund_bid_price), 4)
		elif self.switch_by == "Full Balance":
			self.switch_units = available_units

		if self.switch_units <= 0:
			frappe.throw(_("Switch units must be greater than zero."))

		if self.switch_units > available_units:
			frappe.throw(
				_(
					"Insufficient units. Requested switch units ({0:,.4f}) exceed available units ({1:,.4f}) in source fund as of {2}."
				).format(self.switch_units, available_units, self.switch_date)
			)

		self.gross_switch_amount = round(flt(self.switch_units) * flt(self.from_fund_bid_price), 2)
		self.switch_fee_amount = round(
			flt(self.gross_switch_amount) * (flt(self.switch_fee_pct or 0.0) / 100.0), 2
		)
		self.net_switch_amount = round(flt(self.gross_switch_amount) - flt(self.switch_fee_amount), 2)
		self.units_allocated_to_fund = round(flt(self.net_switch_amount) / flt(self.to_fund_offer_price), 4)

	def before_submit(self):
		if not self.approved_by_checker:
			frappe.throw(
				_("Inter-Fund Switch requires Checker sign-off (approved_by_checker = 1) before submission.")
			)
		if self.maker and self.checker and self.maker == self.checker:
			frappe.throw(
				_("Maker and Checker cannot be the same user for Fund Switch {0}.").format(self.name)
			)

	def on_submit(self):
		"""Executes inter-fund switch: redeems from source and subscribes into target fund via unit ledger."""
		# 1. Post to Immutable Unit Ledger
		make_unit_ledger_entry(
			self,
			[
				{
					"investor": self.investor,
					"fund": self.from_fund,
					"entry_type": "Switch Out",
					"units": -self.switch_units,
					"price_per_unit": self.from_fund_bid_price,
					"amount": self.gross_switch_amount,
					"posting_date": self.switch_date,
				},
				{
					"investor": self.investor,
					"fund": self.to_fund,
					"entry_type": "Switch In",
					"units": self.units_allocated_to_fund,
					"price_per_unit": self.to_fund_offer_price,
					"amount": self.net_switch_amount,
					"posting_date": self.switch_date,
				},
			],
		)

		# 2. Rebuild both source and target portfolios
		rebuild_portfolio(self.investor, self.from_fund)
		rebuild_portfolio(self.investor, self.to_fund)

		source_pid = f"{self.investor}-{self.from_fund}"
		source_port = frappe.get_doc("Asset Investor Portfolio", source_pid)
		target_pid = f"{self.investor}-{self.to_fund}"
		target_port = frappe.get_doc("Asset Investor Portfolio", target_pid)

		# 3. Post Unit Register Entries (Outflow & Inflow) for UI continuity
		reg_out = frappe.new_doc("Asset Investor Register Line")
		reg_out.posting_date = self.switch_date
		reg_out.value_date = self.switch_date
		reg_out.investor = self.investor
		reg_out.portfolio = source_port.name
		reg_out.fund = self.from_fund
		reg_out.entry_type = "Switch Out"
		reg_out.voucher_type = "Asset Fund Switch"
		reg_out.voucher_no = self.name
		reg_out.units = -self.switch_units
		reg_out.nav_per_unit = self.from_fund_bid_price
		reg_out.running_unit_balance = source_port.total_units
		reg_out.gross_amount = -self.gross_switch_amount
		reg_out.fees = self.switch_fee_amount
		reg_out.net_amount = -self.gross_switch_amount
		reg_out.insert(ignore_permissions=True)

		reg_in = frappe.new_doc("Asset Investor Register Line")
		reg_in.posting_date = self.switch_date
		reg_in.value_date = self.switch_date
		reg_in.investor = self.investor
		reg_in.portfolio = target_port.name
		reg_in.fund = self.to_fund
		reg_in.entry_type = "Switch In"
		reg_in.voucher_type = "Asset Fund Switch"
		reg_in.voucher_no = self.name
		reg_in.units = self.units_allocated_to_fund
		reg_in.nav_per_unit = self.to_fund_offer_price
		reg_in.running_unit_balance = target_port.total_units
		reg_in.gross_amount = self.net_switch_amount
		reg_in.fees = 0.0
		reg_in.net_amount = self.net_switch_amount
		reg_in.insert(ignore_permissions=True)

		self.db_set("status", "Submitted")

	def on_cancel(self):
		"""Reverses switch in unit ledger and rebuilds source and target portfolios."""
		reverse_unit_ledger_entries("Asset Fund Switch", self.name)
		rebuild_portfolio(self.investor, self.from_fund)
		rebuild_portfolio(self.investor, self.to_fund)
		self.db_set("status", "Cancelled")
