import frappe
from frappe import _
from frappe.model.document import Document

class AssetInvestorPortfolio(Document):
    def validate(self):
        if self.investor:
            inv = frappe.get_doc("Asset Investor", self.investor)
            self.investor_name = inv.investor_name
            if not self.bank_name and inv.bank_name:
                self.bank_name = inv.bank_name
                self.bank_branch = inv.bank_branch
                self.bank_account_name = inv.bank_account_name
                self.bank_account_no = inv.bank_account_no

        if self.fund:
            fund = frappe.get_doc("Asset Fund", self.fund)
            self.fund_name = fund.fund_name
            if not self.currency:
                self.currency = fund.currency

        self.recalculate_valuation()

    def recalculate_valuation(self, nav_price=None):
        """Updates unit valuation and unrealized gain/loss."""
        if nav_price is None and self.fund:
            nav_price = frappe.db.get_value("Asset Fund", self.fund, "current_nav_per_unit") or 100.0

        if nav_price is not None:
            self.current_nav_per_unit = float(nav_price)

        self.total_units = round(self.total_units or 0.0, 4)
        self.total_invested_amount = round(self.total_invested_amount or 0.0, 2)
        self.total_withdrawn_amount = round(self.total_withdrawn_amount or 0.0, 2)
        self.current_market_value = round(self.total_units * (self.current_nav_per_unit or 0.0), 2)
        
        net_cash_invested = self.total_invested_amount - self.total_withdrawn_amount
        self.unrealized_gain_loss = round(self.current_market_value - net_cash_invested, 2)
