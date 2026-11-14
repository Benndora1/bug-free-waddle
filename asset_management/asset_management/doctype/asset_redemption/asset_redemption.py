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


class AssetRedemption(Document):
	def validate(self):
		if not self.redemption_date:
			self.redemption_date = nowdate()
		if not self.value_date:
			self.value_date = self.redemption_date

		# 1. Validate Investor
		inv = frappe.get_doc("Asset Investor", self.investor)
		self.investor_name = inv.investor_name
		if inv.status != "Active":
			frappe.throw(
				_(
					"Investor {0} is currently {1}. Redemptions cannot be processed for inactive accounts."
				).format(self.investor, inv.status)
			)

		# 2. Validate Fund
		fund = frappe.get_doc("Asset Fund", self.fund)
		self.fund_name = fund.fund_name
		if not self.currency:
			self.currency = fund.currency

		# 3. RULE 1 ENFORCEMENT: Prior-Day Valuation Guard (User Manual Chapter 1.5)
		if not fund.prior_day_valuation_approved or not self.prior_day_valuation_approved:
			frappe.throw(
				_(
					"Operational Regulations Rule 1: Valuation for prior day (T-1) must be formally approved before processing any redemption for fund {0}."
				).format(fund.fund_name)
			)

		# 4. Check Investor Unit Balance from Immutable Ledger
		portfolio_id = f"{self.investor}-{self.fund}"
		self.portfolio = portfolio_id
		available_units = get_unit_balance(self.investor, self.fund, self.redemption_date)
		self.available_portfolio_units = float(available_units)

		if self.available_portfolio_units <= 0:
			frappe.throw(
				_(
					"Insufficient units. Investor {0} holds 0.0 units in fund {1} as of {2}. Redemption cannot proceed."
				).format(self.investor, fund.fund_name, self.redemption_date)
			)

		# 5. Applicable Bid Price (Redemption Price)
		if not self.applicable_bid_price or self.applicable_bid_price <= 0:
			self.applicable_bid_price = fund.current_bid_price or fund.current_nav_per_unit or 100.0

		# 6. Determine Units to Redeem
		if self.redemption_by == "Units":
			if not self.requested_units or self.requested_units <= 0:
				frappe.throw(_("Please specify a valid requested unit quantity."))
			self.units_to_redeem = round(flt(self.requested_units), 4)
		elif self.redemption_by == "Amount":
			if not self.requested_amount or self.requested_amount <= 0:
				frappe.throw(_("Please specify a valid requested redemption amount."))
			self.units_to_redeem = round(flt(self.requested_amount) / flt(self.applicable_bid_price), 4)
		elif self.redemption_by == "Full Liquidation":
			self.units_to_redeem = self.available_portfolio_units

		# Guard against overdraft of units
		if self.units_to_redeem > self.available_portfolio_units:
			frappe.throw(
				_(
					"Insufficient units. Investor {0} holds {1:,.4f} units in fund {2} as of {3}, but requested redemption of {4:,.4f} units."
				).format(
					self.investor,
					self.available_portfolio_units,
					fund.fund_name,
					self.redemption_date,
					self.units_to_redeem,
				)
			)

		if self.units_to_redeem <= 0:
			frappe.throw(_("Units to redeem must be greater than zero."))

		# 7. Calculate Financial Settlements & Deductions
		self.gross_redemption_amount = round(flt(self.units_to_redeem) * flt(self.applicable_bid_price), 2)

		# Check Minimum Redemption Threshold (unless full liquidation)
		if self.redemption_by != "Full Liquidation":
			min_red = fund.min_redemption_amount or 0.0
			if self.gross_redemption_amount < min_red:
				frappe.throw(
					_(
						"Gross redemption amount ({0:,.2f} {1}) is below the minimum allowed redemption limit ({2:,.2f} {1})."
					).format(self.gross_redemption_amount, fund.currency, min_red)
				)

		# Early exit penalty
		self.exit_fee_amount = round(flt(self.gross_redemption_amount) * (flt(self.exit_fee_pct) / 100.0), 2)

		# Withholding Tax (WHT, default 15%)
		taxable_base = max(0.0, flt(self.gross_redemption_amount) - flt(self.exit_fee_amount))
		self.withholding_tax_amount = round(taxable_base * (flt(self.withholding_tax_pct or 15.0) / 100.0), 2)

		# Net Payout Amount
		self.net_payout_amount = round(
			flt(self.gross_redemption_amount) - flt(self.exit_fee_amount) - flt(self.withholding_tax_amount),
			2,
		)
		self.remaining_units = round(flt(self.available_portfolio_units) - flt(self.units_to_redeem), 4)

		# 8. Minimum Retained Balance Guard
		if self.remaining_units > 0:
			remaining_val = round(flt(self.remaining_units) * flt(self.applicable_bid_price), 2)
			min_bal = fund.min_balance_amount or 0.0
			if remaining_val < min_bal:
				frappe.throw(
					_(
						"Redemption leaves remaining portfolio balance ({0:,.2f} {1}), which is below the required fund minimum retained balance ({2:,.2f} {1}). Investor must execute Full Liquidation or reduce redemption amount."
					).format(remaining_val, fund.currency, min_bal)
				)

		# 9. Settlement Bank Details
		if not self.settlement_bank_account_no and inv.bank_account_no:
			self.settlement_bank_name = inv.bank_name
			self.settlement_bank_branch = inv.bank_branch
			self.settlement_bank_account_name = inv.bank_account_name
			self.settlement_bank_account_no = inv.bank_account_no

	def before_submit(self):
		"""Enforces Maker-Checker dual control on redemptions."""
		if not self.checker_approved:
			frappe.throw(
				_(
					"Redemption {0} requires explicit Checker sign-off (checker_approved = 1) before submission."
				).format(self.name)
			)
		if self.maker and self.checker and self.maker == self.checker:
			frappe.throw(_("Maker and Checker cannot be the same user for Redemption {0}.").format(self.name))

	def on_submit(self):
		"""Deducts units via immutable unit ledger, rebuilds portfolio, and flags payment."""
		# 1. Post to Immutable Unit Ledger
		make_unit_ledger_entry(
			self,
			[
				{
					"investor": self.investor,
					"fund": self.fund,
					"entry_type": "Redemption",
					"units": -self.units_to_redeem,
					"price_per_unit": self.applicable_bid_price,
					"amount": self.net_payout_amount,
					"posting_date": self.redemption_date,
				}
			],
		)

		# 2. Rebuild Investor Portfolio from ledger
		rebuild_portfolio(self.investor, self.fund)
		portfolio = frappe.get_doc("Asset Investor Portfolio", self.portfolio)

		# 3. Create Unit Holder Register Entry for UI continuity
		reg = frappe.new_doc("Asset Investor Register Line")
		reg.posting_date = self.redemption_date
		reg.value_date = self.value_date
		reg.investor = self.investor
		reg.portfolio = self.portfolio
		reg.fund = self.fund
		reg.entry_type = "Redemption"
		reg.voucher_type = "Asset Redemption"
		reg.voucher_no = self.name
		reg.units = -self.units_to_redeem
		reg.nav_per_unit = self.applicable_bid_price
		reg.running_unit_balance = portfolio.total_units
		reg.gross_amount = -self.gross_redemption_amount
		reg.fees = self.exit_fee_amount + self.withholding_tax_amount
		reg.net_amount = -self.net_payout_amount
		reg.running_cash_balance = portfolio.total_invested_amount - portfolio.total_withdrawn_amount
		reg.insert(ignore_permissions=True)

		self.db_set("payment_status", "Pending Payment")
		self.db_set("status", "Submitted")

	def on_cancel(self):
		"""Reverses redemption in unit ledger and rebuilds portfolio."""
		reverse_unit_ledger_entries("Asset Redemption", self.name)
		rebuild_portfolio(self.investor, self.fund)
		self.db_set("status", "Cancelled")
