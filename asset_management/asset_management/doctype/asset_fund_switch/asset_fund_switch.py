import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate, flt

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

        source_pid = f"{self.investor}-{self.from_fund}"
        if not frappe.db.exists("Asset Investor Portfolio", source_pid):
            frappe.throw(_("Investor {0} has no portfolio in source fund {1}.").format(self.investor, from_fund.fund_name))

        source_portfolio = frappe.get_doc("Asset Investor Portfolio", source_pid)
        available_units = flt(source_portfolio.total_units)

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
            frappe.throw(_("Requested switch units ({0:,.4f}) exceed available units ({1:,.4f}) in source fund.").format(self.switch_units, available_units))

        self.gross_switch_amount = round(flt(self.switch_units) * flt(self.from_fund_bid_price), 2)
        self.switch_fee_amount = round(flt(self.gross_switch_amount) * (flt(self.switch_fee_pct or 0.0) / 100.0), 2)
        self.net_switch_amount = round(flt(self.gross_switch_amount) - flt(self.switch_fee_amount), 2)
        self.units_allocated_to_fund = round(flt(self.net_switch_amount) / flt(self.to_fund_offer_price), 4)

    def before_submit(self):
        if not self.approved_by_checker:
            frappe.throw(_("Inter-Fund Switch requires Checker sign-off (approved_by_checker = 1) before submission."))
        if self.maker and self.checker and self.maker == self.checker:
            frappe.throw(_("Maker and Checker cannot be the same user for Fund Switch {0}.").format(self.name))

    def on_submit(self):
        """Executes inter-fund switch: redeems from source and subscribes into target fund."""
        # 1. Deduct from Source Portfolio
        source_pid = f"{self.investor}-{self.from_fund}"
        source_port = frappe.get_doc("Asset Investor Portfolio", source_pid)
        source_port.total_units = round(max(0.0, flt(source_port.total_units) - flt(self.switch_units)), 4)
        source_port.total_withdrawn_amount = round(flt(source_port.total_withdrawn_amount) + flt(self.gross_switch_amount), 2)
        source_port.last_transaction_date = self.switch_date
        source_port.recalculate_valuation(self.from_fund_bid_price)
        source_port.save(ignore_permissions=True)

        # 2. Add to Target Portfolio
        target_pid = f"{self.investor}-{self.to_fund}"
        if frappe.db.exists("Asset Investor Portfolio", target_pid):
            target_port = frappe.get_doc("Asset Investor Portfolio", target_pid)
        else:
            target_port = frappe.new_doc("Asset Investor Portfolio")
            target_port.name = target_pid
            target_port.investor = self.investor
            target_port.fund = self.to_fund
            target_port.total_units = 0.0
            target_port.total_invested_amount = 0.0
            target_port.total_withdrawn_amount = 0.0
            target_port.first_subscription_date = self.switch_date

        target_port.total_units = round(flt(target_port.total_units) + flt(self.units_allocated_to_fund), 4)
        target_port.total_invested_amount = round(flt(target_port.total_invested_amount) + flt(self.net_switch_amount), 2)
        target_port.last_transaction_date = self.switch_date
        target_port.recalculate_valuation(self.to_fund_offer_price)
        target_port.save(ignore_permissions=True)

        # 3. Post Unit Register Entries (Outflow & Inflow)
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

        # 4. Update Fund Total Units in Issue
        from_fund_doc = frappe.get_doc("Asset Fund", self.from_fund)
        from_fund_doc.update_units_in_issue(-self.switch_units)

        to_fund_doc = frappe.get_doc("Asset Fund", self.to_fund)
        to_fund_doc.update_units_in_issue(self.units_allocated_to_fund)

        self.db_set("status", "Submitted")
