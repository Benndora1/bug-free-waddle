import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate, flt

class AssetFundValuation(Document):
    def validate(self):
        if not self.valuation_date:
            self.valuation_date = nowdate()

        # 1. Resolve Fund Details
        fund = frappe.get_doc("Asset Fund", self.fund)
        self.fund_name = fund.fund_name
        self.currency = fund.currency
        self.bid_offer_spread_pct = fund.bid_offer_spread_pct or 0.0
        self.previous_nav_per_unit = fund.current_nav_per_unit or 100.0
        self.total_units_in_issue = fund.total_units_in_issue or 0.0

        # 2. Auto-load active holdings if lines empty
        if not self.lines:
            self.load_active_holdings()

        # 3. Aggregate Gross Asset Value (GAV)
        self.aggregate_gav()

        # 4. Accrue Daily Expenses based on Fund Fee Schedule
        self.calculate_daily_accrued_expenses(fund)

        # 5. Calculate NAV & Pricing Output
        self.calculate_nav_and_prices()

    def load_active_holdings(self):
        """Loads all active securities holdings for this fund."""
        holdings = frappe.get_all(
            "Asset Portfolio Holding",
            filters={"fund": self.fund, "holding_status": "Active"},
            fields=["security", "asset_class", "face_value", "carrying_cost", "accrued_interest", "dirty_market_value"]
        )
        self.lines = []
        for h in holdings:
            sec_name = frappe.db.get_value("Asset Investment Security", h.security, "security_name") or h.security
            mkt_price = frappe.db.get_value("Asset Investment Security", h.security, "current_market_price") or 100.0
            self.append("lines", {
                "asset_class": h.asset_class,
                "security": h.security,
                "security_name": sec_name,
                "face_value": h.face_value,
                "price": mkt_price,
                "accrued_interest": h.accrued_interest,
                "dirty_market_value": h.dirty_market_value or (h.carrying_cost + h.accrued_interest)
            })

    def aggregate_gav(self):
        """Sums holding market values and cash accounts to establish GAV."""
        bonds = 0.0
        tbills = 0.0
        deposits = 0.0
        equities = 0.0

        for l in self.lines:
            mv = flt(l.dirty_market_value)
            if l.asset_class in ("Treasury Bond", "Corporate Bond"):
                bonds += mv
            elif l.asset_class in ("Treasury Bill", "Commercial Paper"):
                tbills += mv
            elif l.asset_class in ("Fixed Deposit", "Call Deposit"):
                deposits += mv
            elif l.asset_class == "Quoted Equity":
                equities += mv

        self.bonds_market_value = round(bonds, 2)
        self.tbills_market_value = round(tbills, 2)
        self.deposits_market_value = round(deposits, 2)
        self.equities_market_value = round(equities, 2)
        self.cash_bank_balance = round(flt(self.cash_bank_balance or 0.0), 2)
        self.accrued_income_receivable = round(flt(self.accrued_income_receivable or 0.0), 2)

        holdings_subtotal = self.bonds_market_value + self.tbills_market_value + self.deposits_market_value + self.equities_market_value
        self.total_gav = round(holdings_subtotal + self.cash_bank_balance + self.accrued_income_receivable, 2)

        # Update percentage weights on lines
        if self.total_gav > 0:
            for l in self.lines:
                l.weight_pct = round((flt(l.dirty_market_value) / self.total_gav) * 100.0, 2)

    def calculate_daily_accrued_expenses(self, fund):
        """Computes daily fee accruals reproducing FundValuation.Codeunit.al."""
        # Fee rate lookups
        mgmt_rate = 1.50
        custody_rate = 0.15
        trustee_rate = 0.10
        cma_rate = 0.05
        audit_rate = 0.05

        if fund.fees:
            for f in fund.fees:
                if f.fee_type == "Management Fee":
                    mgmt_rate = flt(f.annual_percentage)
                elif f.fee_type == "Custody Fee":
                    custody_rate = flt(f.annual_percentage)
                elif f.fee_type == "Trustee Fee":
                    trustee_rate = flt(f.annual_percentage)
                elif f.fee_type == "Regulatory Fee (CMA)":
                    cma_rate = flt(f.annual_percentage)
                elif f.fee_type == "Audit Fee":
                    audit_rate = flt(f.annual_percentage)

        # Daily Accrual Formula: GAV * (Rate / 100) / 365
        self.management_fee_accrual = round(self.total_gav * (mgmt_rate / 100.0) / 365.0, 2)
        self.custody_fee_accrual = round(self.total_gav * (custody_rate / 100.0) / 365.0, 2)
        self.trustee_fee_accrual = round(self.total_gav * (trustee_rate / 100.0) / 365.0, 2)
        self.cma_regulatory_fee_accrual = round(self.total_gav * (cma_rate / 100.0) / 365.0, 2)
        self.audit_fee_accrual = round(self.total_gav * (audit_rate / 100.0) / 365.0, 2)
        self.other_liabilities = round(flt(self.other_liabilities or 0.0), 2)

        self.total_accrued_expenses = round(
            self.management_fee_accrual + self.custody_fee_accrual + self.trustee_fee_accrual +
            self.cma_regulatory_fee_accrual + self.audit_fee_accrual + self.other_liabilities,
            2
        )

    def calculate_nav_and_prices(self):
        """Calculates Net Asset Value, NAV per unit, and Bid/Offer spread prices."""
        self.total_nav = round(self.total_gav - self.total_accrued_expenses, 2)

        if self.total_units_in_issue and self.total_units_in_issue > 0:
            self.nav_per_unit = round(self.total_nav / self.total_units_in_issue, 4)
        else:
            self.nav_per_unit = self.previous_nav_per_unit or 100.0

        spread = (self.bid_offer_spread_pct or 0.0) / 100.0
        self.offer_price = round(self.nav_per_unit * (1.0 + spread), 4)
        self.bid_price = round(self.nav_per_unit * (1.0 - spread), 4)

        if self.previous_nav_per_unit and self.previous_nav_per_unit > 0:
            self.daily_change_pct = round(((self.nav_per_unit - self.previous_nav_per_unit) / self.previous_nav_per_unit) * 100.0, 4)
        else:
            self.daily_change_pct = 0.0

    def before_submit(self):
        """Dual control maker-checker validation before valuation approval."""
        if self.prepared_by and self.approved_by and self.prepared_by == self.approved_by:
            frappe.throw(_("Maker (prepared_by) and Checker (approved_by) cannot be the same user for Fund Valuation {0}.").format(self.name))
        if not self.approval_date:
            self.approval_date = nowdate()

    def on_submit(self):
        """Updates fund NAV, unlocks prior-day valuation guard (Rule 1), and revalues client portfolios."""
        fund = frappe.get_doc("Asset Fund", self.fund)
        fund.current_nav_per_unit = self.nav_per_unit
        fund.current_offer_price = self.offer_price
        fund.current_bid_price = self.bid_price
        fund.total_gav = self.total_gav
        fund.total_nav = self.total_nav
        fund.last_valuation_date = self.valuation_date
        # Unlock next-day redemptions under Foundational Rule 1!
        fund.prior_day_valuation_approved = 1
        fund.save(ignore_permissions=True)

        # Mark-to-market revaluation of all client portfolios in this fund
        portfolios = frappe.get_all("Asset Investor Portfolio", filters={"fund": self.fund}, pluck="name")
        for pid in portfolios:
            port = frappe.get_doc("Asset Investor Portfolio", pid)
            port.recalculate_valuation(self.nav_per_unit)
            port.save(ignore_permissions=True)

        self.db_set("status", "Approved")

    def on_cancel(self):
        self.db_set("status", "Cancelled")
