from decimal import ROUND_HALF_UP, Decimal

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, nowdate

from asset_management.accounting.posting import get_accounting_settings, post_gl, reverse_gl
from asset_management.services.pricing import (
	calculate_redemption_pricing,
	calculate_units_for_redemption_amount,
	get_applicable_bid_price,
)
from asset_management.services.units import (
	get_active_lien_units,
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

		if not self.maker:
			self.maker = getattr(self, "owner", None) or frappe.session.user

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

		# 3. RULE 1 ENFORCEMENT: Prior-Day Valuation Guard
		if self.get("prior_day_valuation_approved") is None:
			self.prior_day_valuation_approved = cint(fund.prior_day_valuation_approved)
		if not fund.prior_day_valuation_approved or not cint(self.prior_day_valuation_approved):
			frappe.throw(
				_(
					"Operational Regulations Rule 1: Valuation for prior day (T-1) must be formally approved before processing any redemption for fund {0}."
				).format(fund.fund_name)
			)

		# 4. Check Investor Unit Balance and Active Liens from Immutable Ledger (no max(0, ...))
		portfolio_id = f"{self.investor}-{self.fund}"
		self.portfolio = portfolio_id

		total_units = get_unit_balance(self.investor, self.fund, self.redemption_date)
		lien_units = get_active_lien_units(self.investor, self.fund, self.redemption_date)
		free_units = total_units - lien_units
		self.available_portfolio_units = float(free_units)

		if free_units <= Decimal("0.000000"):
			frappe.throw(
				_(
					"Insufficient units. Investor {0} holds {1} total units with {2} encumbered under active liens in fund {3} as of {4}."
				).format(self.investor, total_units, lien_units, fund.fund_name, self.redemption_date)
			)

		req_units = Decimal("0.000000")
		if self.redemption_by == "Units":
			if not self.requested_units or flt(self.requested_units, 6) <= 0:
				frappe.throw(_("Please specify a valid requested unit quantity."))
			req_units = Decimal(str(self.requested_units)).quantize(
				Decimal("0.000001"), rounding=ROUND_HALF_UP
			)
			if req_units > free_units:
				frappe.throw(
					_(
						"Insufficient units. Investor {0} has {1} free units (total {2} minus {3} active liens) in fund {4} as of {5}, but requested redemption of {6} units."
					).format(
						self.investor,
						free_units,
						total_units,
						lien_units,
						fund.fund_name,
						self.redemption_date,
						req_units,
					)
				)
		elif self.redemption_by == "Amount":
			if not self.requested_amount or flt(self.requested_amount, 2) <= 0:
				frappe.throw(_("Please specify a valid requested redemption amount."))

		# 5. Forward Pricing & Pending Price check (no 100.0 fallback)
		published_bid = get_applicable_bid_price(
			self.fund, self.redemption_date, getattr(self, "received_at", None)
		)
		if not published_bid or published_bid <= Decimal("0.000000"):
			self.status = "Pending Price"
			self.applicable_bid_price = 0.0
			self.units_to_redeem = float(req_units) if self.redemption_by == "Units" else 0.0
			self.gross_redemption_amount = 0.0
			self.exit_fee_amount = 0.0
			self.withholding_tax_amount = 0.0
			self.net_payout_amount = 0.0
			self.remaining_units = (
				float(total_units - req_units) if self.redemption_by == "Units" else float(total_units)
			)
			return

		self.applicable_bid_price = float(published_bid)

		# 6. Determine exact Units to Redeem (6 dp)
		if self.redemption_by == "Units":
			u_to_redeem = req_units
		elif self.redemption_by == "Amount":
			u_to_redeem = calculate_units_for_redemption_amount(self.requested_amount, published_bid)
		elif self.redemption_by == "Full Liquidation":
			u_to_redeem = free_units
		else:
			u_to_redeem = req_units

		if u_to_redeem <= Decimal("0.000000"):
			frappe.throw(_("Units to redeem must be greater than zero."))

		if u_to_redeem > free_units:
			frappe.throw(
				_(
					"Insufficient units. Investor {0} has {1} free units (total {2} minus {3} active liens) in fund {4} as of {5}, but requested redemption of {6} units."
				).format(
					self.investor,
					free_units,
					total_units,
					lien_units,
					fund.fund_name,
					self.redemption_date,
					u_to_redeem,
				)
			)

		self.units_to_redeem = float(u_to_redeem)

		# 7. Calculate Financial Settlements & Deductions via services/pricing.py
		wht_basis = getattr(fund, "wht_basis", None) or "None"
		wht_rate = (
			self.withholding_tax_pct
			if (self.withholding_tax_pct is not None and flt(self.withholding_tax_pct) > 0)
			else (getattr(fund, "wht_rate", 0.0) or 0.0)
		)
		self.withholding_tax_pct = flt(wht_rate) if wht_basis != "None" else 0.0

		cost_per_unit = Decimal("0.000000")
		if wht_basis == "Gain over Cost" and frappe.db.exists("Asset Investor Portfolio", portfolio_id):
			avg_cost = frappe.db.get_value("Asset Investor Portfolio", portfolio_id, "average_cost_per_unit")
			if avg_cost:
				cost_per_unit = Decimal(str(avg_cost))

		pricing = calculate_redemption_pricing(
			units=u_to_redeem,
			bid_price=published_bid,
			exit_fee_pct=self.exit_fee_pct or 0.0,
			wht_rate=wht_rate,
			wht_basis=wht_basis,
			cost_per_unit=cost_per_unit,
		)

		self.gross_redemption_amount = float(pricing["gross"])
		self.exit_fee_amount = float(pricing["exit_fee"])
		self.withholding_tax_amount = float(pricing["wht"])
		self.net_payout_amount = float(pricing["net"])
		self.remaining_units = float((total_units - u_to_redeem).quantize(Decimal("0.000001")))

		if self.status == "Pending Price":
			self.status = "Draft"

		# Check Minimum Redemption Threshold (unless full liquidation)
		if self.redemption_by != "Full Liquidation":
			min_red = flt(fund.min_redemption_amount)
			if min_red > 0 and self.gross_redemption_amount < min_red:
				frappe.throw(
					_(
						"Gross redemption amount ({0:,.2f} {1}) is below the minimum allowed redemption limit ({2:,.2f} {1})."
					).format(self.gross_redemption_amount, fund.currency, min_red)
				)

		# 8. Minimum Retained Balance Guard
		if self.remaining_units > 0:
			remaining_val = float(
				(Decimal(str(self.remaining_units)) * published_bid).quantize(
					Decimal("0.01"), rounding=ROUND_HALF_UP
				)
			)
			min_bal = flt(fund.min_balance_amount)
			if min_bal > 0 and remaining_val < min_bal:
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
		"""Enforces Pending Price guard and Maker-Checker dual control on redemptions."""
		if (
			self.status == "Pending Price"
			or not self.applicable_bid_price
			or flt(self.applicable_bid_price, 6) <= 0
		):
			frappe.throw(
				_(
					"Redemption {0} is in 'Pending Price' status and cannot be submitted until a bid price is published for dealing date {1}."
				).format(self.name, self.redemption_date),
				title=_("Pending Price"),
			)

		if not self.checker_approved:
			frappe.throw(
				_(
					"Redemption {0} requires explicit Checker sign-off (checker_approved = 1) before submission."
				).format(self.name)
			)
		maker = self.maker or getattr(self, "owner", None) or frappe.session.user
		if self.checker and maker == self.checker:
			frappe.throw(_("Maker and Checker cannot be the same user for Redemption {0}.").format(self.name))

	def get_gl_entries(self) -> list[dict]:
		"""Constructs the General Ledger map in the fund's company:

		- Dr Unitholders' Capital: gross_redemption_amount
		- Cr Client Cash Payable (party = investor supplier): net_payout_amount
		- Cr Exit Fee Payable (if exit_fee_amount > 0): exit_fee_amount
		- Cr WHT Payable (if withholding_tax_amount > 0): withholding_tax_amount
		"""
		from asset_management.asset_management.doctype.asset_investor.asset_investor import (
			get_or_create_investor_supplier,
		)

		settings = get_accounting_settings()
		fund_doc = frappe.get_doc("Asset Fund", self.fund)

		fund_company = (
			getattr(fund_doc, "company", None)
			or getattr(settings, "default_fund_company", None)
			or getattr(settings, "fund_manager_company", None)
		)

		unitholders_capital_account = getattr(fund_doc, "unitholders_capital_account", None) or getattr(
			settings, "unitholders_capital_account", None
		)
		client_cash_account = getattr(fund_doc, "client_cash_payable_account", None) or getattr(
			settings, "client_cash_payable_account", None
		)
		exit_fee_account = getattr(fund_doc, "exit_fee_payable_account", None) or getattr(
			settings, "exit_fee_payable_account", None
		)
		wht_account = getattr(fund_doc, "wht_payable_account", None) or getattr(
			settings, "wht_payable_account", None
		)

		investor_supplier = get_or_create_investor_supplier(self.investor)

		gl_entries: list[dict] = []

		# Row 1: Dr Unitholders' Capital gross
		gl_entries.append(
			{
				"company": fund_company,
				"account": unitholders_capital_account,
				"debit": flt(self.gross_redemption_amount, 2),
				"credit": 0.0,
				"against": client_cash_account,
				"remarks": _("Redemption of {0} units by investor {1}").format(
					self.units_to_redeem, self.investor
				),
				"posting_date": self.redemption_date,
			}
		)

		# Row 2: Cr Client Cash Payable net (party = investor supplier)
		gl_entries.append(
			{
				"company": fund_company,
				"account": client_cash_account,
				"party_type": "Supplier",
				"party": investor_supplier,
				"debit": 0.0,
				"credit": flt(self.net_payout_amount, 2),
				"against": unitholders_capital_account,
				"remarks": _("Net redemption proceeds payable to investor {0}").format(self.investor),
				"posting_date": self.redemption_date,
			}
		)

		# Row 3: Cr Exit Fee Payable (if > 0)
		if flt(self.exit_fee_amount, 2) > 0:
			gl_entries.append(
				{
					"company": fund_company,
					"account": exit_fee_account,
					"debit": 0.0,
					"credit": flt(self.exit_fee_amount, 2),
					"against": unitholders_capital_account,
					"remarks": _("Exit fee on redemption {0}").format(self.name),
					"posting_date": self.redemption_date,
				}
			)

		# Row 4: Cr WHT Payable (if > 0)
		if flt(self.withholding_tax_amount, 2) > 0:
			gl_entries.append(
				{
					"company": fund_company,
					"account": wht_account,
					"debit": 0.0,
					"credit": flt(self.withholding_tax_amount, 2),
					"against": unitholders_capital_account,
					"remarks": _("Withholding tax on redemption {0}").format(self.name),
					"posting_date": self.redemption_date,
				}
			)

		return gl_entries

	def on_submit(self):
		"""Posts GL entries, deducts units in immutable unit ledger, and rebuilds portfolio."""
		# 1. Post to General Ledger via accounting adapter
		post_gl(self, self.get_gl_entries())

		# 2. Post negative units to Immutable Unit Ledger (No Register Line per R-10)
		make_unit_ledger_entry(
			self,
			[
				{
					"investor": self.investor,
					"fund": self.fund,
					"entry_type": "Redemption",
					"units": -flt(self.units_to_redeem, 6),
					"price_per_unit": flt(self.applicable_bid_price, 6),
					"amount": flt(self.net_payout_amount, 2),
					"currency": self.currency,
					"posting_date": self.redemption_date,
				}
			],
		)

		# 3. Rebuild Investor Portfolio from ledger
		rebuild_portfolio(self.investor, self.fund)

		self.db_set("payment_status", "Pending Payment")
		self.db_set("status", "Submitted")

	def before_cancel(self):
		self.ignore_linked_doctypes = [
			"GL Entry",
			"Payment Ledger Entry",
			"Asset Unit Ledger Entry",
			"Asset Investor Register Line",
		]

	def on_cancel(self):
		"""Reverses redemption in GL and unit ledger, and rebuilds portfolio."""
		reverse_gl(self)
		reverse_unit_ledger_entries("Asset Redemption", self.name)
		rebuild_portfolio(self.investor, self.fund)
		self.db_set("status", "Cancelled")
