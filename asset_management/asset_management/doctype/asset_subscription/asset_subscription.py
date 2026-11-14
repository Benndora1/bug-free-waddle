import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from asset_management.accounting.posting import post_gl, reverse_gl
from asset_management.services.pricing import (
	calculate_subscription_pricing,
	get_applicable_fund_price,
)
from asset_management.services.units import (
	get_unit_balance,
	make_unit_ledger_entry,
	rebuild_portfolio,
	reverse_unit_ledger_entries,
)


class AssetSubscription(Document):
	def validate(self):
		if not self.subscription_date:
			self.subscription_date = nowdate()
		if not self.value_date:
			self.value_date = self.subscription_date

		if not self.maker:
			self.maker = getattr(self, "owner", None) or frappe.session.user

		if not self.gross_amount or self.gross_amount <= 0:
			frappe.throw(_("Gross Subscription Amount must be greater than zero."))

		# 1. Validate Investor
		inv = frappe.get_doc("Asset Investor", self.investor)
		self.investor_name = inv.investor_name
		if inv.status != "Active":
			frappe.throw(
				_(
					"Investor {0} is currently {1}. Subscriptions can only be accepted for Active investors."
				).format(self.investor, inv.status)
			)

		# 2. Validate Fund
		fund = frappe.get_doc("Asset Fund", self.fund)
		self.fund_name = fund.fund_name
		if fund.status != "Active":
			frappe.throw(
				_("Fund {0} is currently {1}. Subscriptions cannot be created.").format(
					self.fund, fund.status
				)
			)

		if not self.currency:
			self.currency = fund.currency

		# 3. Minimum Subscription Threshold Guard (User Manual Chapter 6)
		existing_units = float(get_unit_balance(self.investor, self.fund))

		if existing_units > 0:
			min_required = fund.min_additional_amount or 0.0
			if self.gross_amount < min_required:
				frappe.throw(
					_(
						"Subscription amount ({0:,.2f}) is below the minimum additional subscription limit ({1:,.2f} {2}) for fund {3}."
					).format(self.gross_amount, min_required, fund.currency, fund.fund_name)
				)
		else:
			min_required = fund.min_subscription_amount or 0.0
			if self.gross_amount < min_required:
				frappe.throw(
					_(
						"Subscription amount ({0:,.2f}) is below the initial minimum subscription limit ({1:,.2f} {2}) for fund {3}."
					).format(self.gross_amount, min_required, fund.currency, fund.fund_name)
				)

		# 4. Forward Pricing & Calculations (services/pricing.py) - Remove 100.0 fallback
		published_price = get_applicable_fund_price(self.fund, self.subscription_date)
		if not published_price or published_price <= 0:
			self.status = "Pending Price"
			self.applicable_nav_price = 0.0
			self.units_allocated = 0.0
			self.entry_fee_amount = round(flt(self.gross_amount) * (flt(self.entry_fee_pct) / 100.0), 2)
			self.net_invested_amount = round(flt(self.gross_amount) - self.entry_fee_amount, 2)
		else:
			pricing = calculate_subscription_pricing(
				self.gross_amount, self.entry_fee_pct or 0.0, published_price
			)
			self.applicable_nav_price = float(pricing["offer_price"])
			self.entry_fee_amount = float(pricing["entry_fee"])
			self.net_invested_amount = float(pricing["net_amount"])
			self.units_allocated = float(pricing["units"])
			if self.status == "Pending Price":
				self.status = "Draft"

		# 5. Agent Commission Setup
		if self.agent:
			if not self.agent_commission_pct or self.agent_commission_pct == 0:
				agent_doc = frappe.get_doc("Asset Agent", self.agent)
				self.agent_commission_pct = agent_doc.commission_rate_pct or 0.0
			self.agent_commission_amount = round(
				flt(self.gross_amount) * (flt(self.agent_commission_pct) / 100.0), 2
			)
		else:
			self.agent_commission_pct = 0.0
			self.agent_commission_amount = 0.0

	def before_submit(self):
		"""Enforces Maker-Checker controls and Pending Price guard on subscriptions."""
		# 0. Pending Price Guard
		if self.status == "Pending Price" or not self.applicable_nav_price or self.applicable_nav_price <= 0:
			frappe.throw(
				_(
					"Subscription {0} is in 'Pending Price' status and cannot be submitted until an Asset Fund price is published for dealing date {1}."
				).format(self.name, self.subscription_date),
				title=_("Pending Price"),
			)

		# 1. Approval Guard: Subscription must be approved by Checker prior to unit allocation and posting
		if self.workflow_state and self.workflow_state not in ["Approved", "Submitted"]:
			frappe.throw(
				_(
					"Subscription {0} must be in 'Approved' state before unit allocation and GL posting."
				).format(self.name)
			)

		if (
			not self.approved_by_operations
			and not self.checker
			and not (self.workflow_state and self.workflow_state in ["Approved", "Submitted"])
		):
			frappe.throw(
				_("Subscription {0} requires authorized checker approval before posting.").format(self.name)
			)

		# 2. Dual-Control Rule: Maker cannot be Checker
		maker = self.maker or getattr(self, "owner", None) or frappe.session.user
		if self.checker and maker == self.checker:
			frappe.throw(
				_("Maker and Checker cannot be the same user for Subscription {0}.").format(self.name)
			)

		if not self.approved_by_operations:
			self.approved_by_operations = 1
		if not self.approval_date:
			self.approval_date = nowdate()

	def get_gl_entries(self) -> list[dict]:
		"""Constructs the General Ledger map per .agents/rules/accounting.md:

		Fund Company:
		1. Dr Client Cash Payable (party_type Supplier, party = investor's supplier) gross
		2. Cr Unitholders' Capital net
		3. Cr Entry Fee Payable fee

		Fund Manager Company (if agent commission):
		4. Dr Commission Expense comm_amount
		5. Cr Commission Payable comm_amount
		"""
		from asset_management.accounting.posting import get_accounting_settings
		from asset_management.asset_management.doctype.asset_agent.asset_agent import (
			get_or_create_agent_supplier,
		)
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

		client_cash_account = getattr(fund_doc, "client_cash_payable_account", None) or getattr(
			settings, "client_cash_payable_account", None
		)
		unitholders_capital_account = getattr(fund_doc, "unitholders_capital_account", None) or getattr(
			settings, "unitholders_capital_account", None
		)
		entry_fee_account = getattr(fund_doc, "entry_fee_payable_account", None) or getattr(
			settings, "entry_fee_payable_account", None
		)

		investor_supplier = get_or_create_investor_supplier(self.investor)

		gl_entries: list[dict] = []

		# Row 1: Dr Client Cash Payable gross
		gl_entries.append(
			{
				"company": fund_company,
				"account": client_cash_account,
				"party_type": "Supplier",
				"party": investor_supplier,
				"debit": flt(self.gross_amount),
				"credit": 0.0,
				"against": f"{unitholders_capital_account}, {entry_fee_account}",
				"remarks": _("Subscription unit allotment for investor {0}").format(self.investor),
				"posting_date": self.subscription_date,
			}
		)

		# Row 2: Cr Unitholders' Capital net
		gl_entries.append(
			{
				"company": fund_company,
				"account": unitholders_capital_account,
				"debit": 0.0,
				"credit": flt(self.net_invested_amount),
				"against": client_cash_account,
				"remarks": _("Capital invested for {0} units").format(self.units_allocated),
				"posting_date": self.subscription_date,
			}
		)

		# Row 3: Cr Entry Fee Payable fee
		if flt(self.entry_fee_amount) > 0:
			gl_entries.append(
				{
					"company": fund_company,
					"account": entry_fee_account,
					"debit": 0.0,
					"credit": flt(self.entry_fee_amount),
					"against": client_cash_account,
					"remarks": _("Entry fee accrued on subscription {0}").format(self.name),
					"posting_date": self.subscription_date,
				}
			)

		# Rows 4 & 5: Agent Commission in Fund Manager Company
		if self.agent and flt(self.agent_commission_amount) > 0:
			fm_company = getattr(settings, "fund_manager_company", None) or fund_company
			comm_exp_account = getattr(settings, "commission_expense_account", None)
			comm_pay_account = getattr(settings, "commission_payable_account", None)

			gl_entries.append(
				{
					"company": fm_company,
					"account": comm_exp_account,
					"debit": flt(self.agent_commission_amount),
					"credit": 0.0,
					"against": comm_pay_account,
					"remarks": _("Distribution commission expense for agent {0}").format(self.agent),
					"posting_date": self.subscription_date,
				}
			)
			agent_supplier = get_or_create_agent_supplier(self.agent)
			gl_entries.append(
				{
					"company": fm_company,
					"account": comm_pay_account,
					"party_type": "Supplier",
					"party": agent_supplier,
					"debit": 0.0,
					"credit": flt(self.agent_commission_amount),
					"against": comm_exp_account,
					"remarks": _("Distribution commission payable for agent {0}").format(self.agent),
					"posting_date": self.subscription_date,
				}
			)

		return gl_entries

	def on_submit(self):
		"""Processes GL posting, unit creation, and portfolio rebuild."""
		# 1. Post to General Ledger via accounting adapter
		post_gl(self, self.get_gl_entries())

		# 2. Post to Immutable Unit Ledger
		make_unit_ledger_entry(
			self,
			[
				{
					"investor": self.investor,
					"fund": self.fund,
					"entry_type": "Subscription",
					"units": self.units_allocated,
					"price_per_unit": self.applicable_nav_price,
					"amount": self.gross_amount,
					"currency": self.currency,
					"posting_date": self.subscription_date,
				}
			],
		)

		# 3. Rebuild Investor Portfolio from ledger
		rebuild_portfolio(self.investor, self.fund)
		portfolio_id = f"{self.investor}-{self.fund}"
		portfolio = frappe.get_doc("Asset Investor Portfolio", portfolio_id)

		# 4. Create Unit Holder Register Entry for UI continuity
		reg = frappe.new_doc("Asset Investor Register Line")
		reg.posting_date = self.subscription_date
		reg.value_date = self.value_date
		reg.investor = self.investor
		reg.portfolio = portfolio.name
		reg.fund = self.fund
		reg.entry_type = "Subscription"
		reg.voucher_type = "Asset Subscription"
		reg.voucher_no = self.name
		reg.units = self.units_allocated
		reg.nav_per_unit = self.applicable_nav_price
		reg.running_unit_balance = portfolio.total_units
		reg.gross_amount = self.gross_amount
		reg.fees = self.entry_fee_amount
		reg.net_amount = self.net_invested_amount
		reg.running_cash_balance = portfolio.total_invested_amount
		reg.insert(ignore_permissions=True)

		# 5. Create Agent Commission row if applicable
		if self.agent and self.agent_commission_amount > 0:
			comm = frappe.new_doc("Asset Agent Commission")
			comm.agent = self.agent
			comm.subscription = self.name
			comm.posting_date = self.subscription_date
			comm.investor = self.investor
			comm.fund = self.fund
			comm.gross_subscription_amount = self.gross_amount
			comm.commission_rate_pct = self.agent_commission_pct
			comm.commission_amount = self.agent_commission_amount
			comm.payment_status = "Accrued"
			comm.insert(ignore_permissions=True)

		# Set Contract Note No & Status
		self.db_set("contract_note_no", f"CN-{self.name}")
		self.db_set("status", "Submitted")

	def before_cancel(self):
		self.ignore_linked_doctypes = [
			"GL Entry",
			"Payment Ledger Entry",
			"Asset Unit Ledger Entry",
			"Asset Investor Register Line",
			"Asset Agent Commission",
		]

	def on_cancel(self):
		"""Reverses subscription in GL and unit ledger, cancels commission, and rebuilds portfolio."""
		# 1. Reverse GL entries
		reverse_gl(self)

		# 2. Reverse unit ledger and register line
		reverse_unit_ledger_entries("Asset Subscription", self.name)
		for rname in frappe.get_all(
			"Asset Investor Register Line",
			filters={"voucher_type": "Asset Subscription", "voucher_no": self.name},
			pluck="name",
		):
			frappe.delete_doc("Asset Investor Register Line", rname, force=True, ignore_permissions=True)
		rebuild_portfolio(self.investor, self.fund)

		# 3. Cancel Agent Commission row
		comm_rows = frappe.get_all(
			"Asset Agent Commission", filters={"subscription": self.name}, pluck="name"
		)
		for cname in comm_rows:
			frappe.db.set_value("Asset Agent Commission", cname, "payment_status", "Cancelled")

		self.db_set("status", "Cancelled")
