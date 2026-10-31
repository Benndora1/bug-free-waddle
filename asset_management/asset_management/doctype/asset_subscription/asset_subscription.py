import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate, flt

class AssetSubscription(Document):
    def validate(self):
        if not self.subscription_date:
            self.subscription_date = nowdate()
        if not self.value_date:
            self.value_date = self.subscription_date

        if not self.gross_amount or self.gross_amount <= 0:
            frappe.throw(_("Gross Subscription Amount must be greater than zero."))

        # 1. Validate Investor
        inv = frappe.get_doc("Asset Investor", self.investor)
        self.investor_name = inv.investor_name
        if inv.status != "Active":
            frappe.throw(_("Investor {0} is currently {1}. Subscriptions can only be accepted for Active investors.").format(self.investor, inv.status))

        # 2. Validate Fund
        fund = frappe.get_doc("Asset Fund", self.fund)
        self.fund_name = fund.fund_name
        if fund.status != "Active":
            frappe.throw(_("Fund {0} is currently {1}. Subscriptions cannot be created.").format(self.fund, fund.status))

        if not self.currency:
            self.currency = fund.currency

        # 3. Minimum Subscription Threshold Guard (User Manual Chapter 6)
        portfolio_id = f"{self.investor}-{self.fund}"
        has_existing = frappe.db.exists("Asset Investor Portfolio", portfolio_id)
        existing_units = frappe.db.get_value("Asset Investor Portfolio", portfolio_id, "total_units") or 0.0

        if existing_units > 0:
            min_required = fund.min_additional_amount or 0.0
            if self.gross_amount < min_required:
                frappe.throw(
                    _("Subscription amount ({0:,.2f}) is below the minimum additional subscription limit ({1:,.2f} {2}) for fund {3}.").format(
                        self.gross_amount, min_required, fund.currency, fund.fund_name
                    )
                )
        else:
            min_required = fund.min_subscription_amount or 0.0
            if self.gross_amount < min_required:
                frappe.throw(
                    _("Subscription amount ({0:,.2f}) is below the initial minimum subscription limit ({1:,.2f} {2}) for fund {3}.").format(
                        self.gross_amount, min_required, fund.currency, fund.fund_name
                    )
                )

        # 4. Fee & Unit Allocation Calculation
        self.entry_fee_amount = round(flt(self.gross_amount) * (flt(self.entry_fee_pct) / 100.0), 2)
        self.net_invested_amount = round(flt(self.gross_amount) - self.entry_fee_amount, 2)

        if not self.applicable_nav_price or self.applicable_nav_price <= 0:
            self.applicable_nav_price = fund.current_offer_price or fund.current_nav_per_unit or 100.0

        if self.applicable_nav_price <= 0:
            frappe.throw(_("Applicable Offer Price for fund {0} is invalid ({1}).").format(self.fund, self.applicable_nav_price))

        self.units_allocated = round(flt(self.net_invested_amount) / flt(self.applicable_nav_price), 4)

        # 5. Agent Commission Setup
        if self.agent:
            if not self.agent_commission_pct or self.agent_commission_pct == 0:
                agent_doc = frappe.get_doc("Asset Agent", self.agent)
                self.agent_commission_pct = agent_doc.commission_rate_pct or 0.0
            self.agent_commission_amount = round(flt(self.gross_amount) * (flt(self.agent_commission_pct) / 100.0), 2)
        else:
            self.agent_commission_pct = 0.0
            self.agent_commission_amount = 0.0

    def before_submit(self):
        """Enforces Maker-Checker controls on subscriptions."""
        if self.maker and self.checker and self.maker == self.checker:
            frappe.throw(_("Maker and Checker cannot be the same user for Subscription {0}.").format(self.name))

    def on_submit(self):
        """Processes unit creation, updates portfolio balances and posts register entry (SubRedPosting.Codeunit.al)."""
        portfolio_id = f"{self.investor}-{self.fund}"
        if frappe.db.exists("Asset Investor Portfolio", portfolio_id):
            portfolio = frappe.get_doc("Asset Investor Portfolio", portfolio_id)
        else:
            portfolio = frappe.new_doc("Asset Investor Portfolio")
            portfolio.name = portfolio_id
            portfolio.investor = self.investor
            portfolio.fund = self.fund
            portfolio.currency = self.currency
            portfolio.total_units = 0.0
            portfolio.total_invested_amount = 0.0
            portfolio.total_withdrawn_amount = 0.0
            portfolio.first_subscription_date = self.subscription_date

        portfolio.total_units = round(flt(portfolio.total_units) + flt(self.units_allocated), 4)
        portfolio.total_invested_amount = round(flt(portfolio.total_invested_amount) + flt(self.gross_amount), 2)
        portfolio.last_transaction_date = self.subscription_date
        portfolio.recalculate_valuation(self.applicable_nav_price)
        portfolio.save(ignore_permissions=True)

        # Create Unit Holder Register Entry
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

        # Update Fund Total Units in Issue
        fund_doc = frappe.get_doc("Asset Fund", self.fund)
        fund_doc.update_units_in_issue(self.units_allocated)

        # Create Agent Commission if applicable
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

    def on_cancel(self):
        """Reverses subscription and deducts units from portfolio and fund."""
        portfolio_id = f"{self.investor}-{self.fund}"
        if frappe.db.exists("Asset Investor Portfolio", portfolio_id):
            portfolio = frappe.get_doc("Asset Investor Portfolio", portfolio_id)
            portfolio.total_units = round(max(0.0, flt(portfolio.total_units) - flt(self.units_allocated)), 4)
            portfolio.total_invested_amount = round(max(0.0, flt(portfolio.total_invested_amount) - flt(self.gross_amount)), 2)
            portfolio.recalculate_valuation(self.applicable_nav_price)
            portfolio.save(ignore_permissions=True)

        fund_doc = frappe.get_doc("Asset Fund", self.fund)
        fund_doc.update_units_in_issue(-self.units_allocated)
        self.db_set("status", "Cancelled")
