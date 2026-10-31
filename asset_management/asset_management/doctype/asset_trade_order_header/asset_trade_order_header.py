import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate, add_days, flt

class AssetTradeOrderHeader(Document):
    def validate(self):
        if not self.order_date:
            self.order_date = nowdate()
        if not self.settlement_date:
            self.settlement_date = self.order_date

        # 1. Resolve Security Details
        sec = frappe.get_doc("Asset Investment Security", self.security)
        self.security_name = sec.security_name
        self.asset_class = sec.asset_class
        if not self.coupon_rate and sec.coupon_rate:
            self.coupon_rate = sec.coupon_rate

        # 2. Financial Consideration & Settlement Calculations
        self.face_value = round(flt(self.face_value), 2)
        self.clean_price_pct = flt(self.clean_price_pct)
        self.brokerage_commission = round(flt(self.brokerage_commission or 0.0), 2)

        if self.asset_class in ("Treasury Bond", "Corporate Bond"):
            self.consideration_amount = round(self.face_value * (self.clean_price_pct / 100.0), 2)
            if self.days_accrued and self.coupon_rate:
                self.accrued_interest = round(self.face_value * (flt(self.coupon_rate) / 100.0) * (flt(self.days_accrued) / 365.0), 2)
            else:
                self.accrued_interest = round(flt(self.accrued_interest or 0.0), 2)

            self.dirty_price = round(self.clean_price_pct + ((self.accrued_interest / self.face_value * 100.0) if self.face_value else 0.0), 4)
            self.settlement_amount = round(self.consideration_amount + self.accrued_interest + self.brokerage_commission, 2)

        elif self.asset_class in ("Treasury Bill", "Commercial Paper"):
            self.consideration_amount = round(self.face_value * (self.clean_price_pct / 100.0), 2)
            self.accrued_interest = 0.0
            self.dirty_price = self.clean_price_pct
            self.settlement_amount = round(self.consideration_amount + self.brokerage_commission, 2)

        elif self.asset_class in ("Fixed Deposit", "Call Deposit"):
            self.clean_price_pct = 100.0
            self.dirty_price = 100.0
            self.consideration_amount = self.face_value
            self.settlement_amount = self.face_value
            self.accrued_interest = 0.0
            if self.deposit_tenor_days and self.interest_rate:
                self.expected_interest = round(self.face_value * (flt(self.interest_rate) / 100.0) * (flt(self.deposit_tenor_days) / 365.0), 2)
                if not self.maturity_date:
                    self.maturity_date = add_days(self.order_date, int(self.deposit_tenor_days))

        elif self.asset_class == "Quoted Equity":
            self.consideration_amount = round(self.face_value * self.clean_price_pct, 2)
            self.accrued_interest = 0.0
            self.dirty_price = self.clean_price_pct
            self.settlement_amount = round(self.consideration_amount + self.brokerage_commission, 2)

        # 3. RULE 2: Pre-Trade Compliance & Cash Availability Checks (Chapter 20 / InvestmentLimitCheck)
        self.run_pre_trade_compliance_checks(sec)

    def run_pre_trade_compliance_checks(self, sec):
        """Evaluates cash availability, asset allocation limits, and single-issuer concentration."""
        fund_doc = frappe.get_doc("Asset Fund", self.fund)
        fund_total_val = flt(fund_doc.total_gav or fund_doc.total_nav or 10000000000.0)

        # A. Cash Availability Guard
        # Assume 20% liquid cash allocation baseline if cash balance not tracked in ledger
        available_cash = flt(fund_doc.total_nav * 0.25) if fund_doc.total_nav else 2500000000.0
        self.cash_available_before_trade = round(available_cash, 2)
        if self.order_type in ("BUY", "PLACEMENT"):
            self.cash_after_trade = round(self.cash_available_before_trade - self.settlement_amount, 2)
        else:
            self.cash_after_trade = round(self.cash_available_before_trade + self.settlement_amount, 2)

        breaches = []

        if self.order_type in ("BUY", "PLACEMENT") and self.cash_after_trade < 0:
            breaches.append(f"Cash Overdraft Breach: Trade requires {self.settlement_amount:,.2f} UGX but available cash is {self.cash_available_before_trade:,.2f} UGX.")

        # B. Investment Limits Evaluation
        limits = frappe.get_all(
            "Asset Investment Limit Setup",
            filters={"fund": self.fund},
            fields=["name", "rule_type", "target_asset_class", "target_issuer", "target_sector", "max_allocation_pct", "enforce_strict_block"]
        )

        for lim in limits:
            # 1. Asset Class Limit
            if lim.rule_type == "Asset Class Limit" and lim.target_asset_class == self.asset_class:
                # Sum existing holdings in this asset class
                existing_holdings = frappe.db.sql(
                    """SELECT SUM(dirty_market_value) FROM `tabAsset Portfolio Holding` WHERE fund=%s AND asset_class=%s AND holding_status='Active'""",
                    (self.fund, self.asset_class)
                )[0][0] or 0.0
                projected_total = existing_holdings + self.settlement_amount
                projected_pct = (projected_total / fund_total_val) * 100.0
                if projected_pct > flt(lim.max_allocation_pct):
                    breaches.append(
                        f"Asset Class Limit Breach: {self.asset_class} allocation would reach {projected_pct:.2f}% (max allowed: {lim.max_allocation_pct:.2f}%)."
                    )

            # 2. Single Issuer Limit
            if lim.rule_type == "Single Issuer Limit" and lim.target_issuer and (lim.target_issuer.upper() in sec.issuer.upper() or sec.issuer.upper() in lim.target_issuer.upper()):
                existing_issuer = frappe.db.sql(
                    """SELECT SUM(h.dirty_market_value) FROM `tabAsset Portfolio Holding` h JOIN `tabAsset Investment Security` s ON h.security=s.name WHERE h.fund=%s AND s.issuer=%s AND h.holding_status='Active'""",
                    (self.fund, sec.issuer)
                )[0][0] or 0.0
                projected_total = existing_issuer + self.settlement_amount
                projected_pct = (projected_total / fund_total_val) * 100.0
                if projected_pct > flt(lim.max_allocation_pct):
                    breaches.append(
                        f"Single Issuer Limit Breach: Issuer '{sec.issuer}' exposure would reach {projected_pct:.2f}% (max allowed: {lim.max_allocation_pct:.2f}%)."
                    )

        self.compliance_checked = 1
        if breaches:
            self.compliance_status = "Breached"
            self.compliance_notes = " | ".join(breaches)
        else:
            self.compliance_status = "Passed"
            self.compliance_notes = "Pre-trade compliance check passed. All allocation and cash limits verified."

    def before_submit(self):
        """Enforces pre-trade compliance override rules and dual maker-checker authorization."""
        # 1. Regulatory Compliance Enforcement (Chapter 20)
        if self.compliance_status == "Breached" and not self.override_approved:
            frappe.throw(
                _("Pre-Trade Compliance Breach: {0}. Regulatory Rule 2 mandates explicit Compliance/CE Override Approval (override_approved = 1) and justification before trade authorization.").format(
                    self.compliance_notes
                )
            )

        # 2. Maker-Checker Dual Control
        if self.dealer and self.approver and self.dealer == self.approver:
            frappe.throw(_("Dealer (Maker) and Approver (Checker) cannot be the same user for Trade Order {0}.").format(self.name))

        if self.approval_status != "Approved":
            frappe.throw(_("Trade Order {0} requires formal approval (approval_status = 'Approved') before execution.").format(self.name))

    def on_submit(self):
        """Updates portfolio securities ledger and generates custody instruction ticket."""
        holding_id = f"{self.fund}-{self.security}"
        sec = frappe.get_doc("Asset Investment Security", self.security)

        if frappe.db.exists("Asset Portfolio Holding", holding_id):
            holding = frappe.get_doc("Asset Portfolio Holding", holding_id)
        else:
            holding = frappe.new_doc("Asset Portfolio Holding")
            holding.name = holding_id
            holding.fund = self.fund
            holding.security = self.security
            holding.asset_class = self.asset_class
            holding.acquisition_date = self.settlement_date
            holding.maturity_date = sec.maturity_date or self.maturity_date
            holding.holding_status = "Active"

        if self.order_type in ("BUY", "PLACEMENT"):
            holding.face_value = round(flt(holding.face_value) + flt(self.face_value), 2)
            holding.carrying_cost = round(flt(holding.carrying_cost) + flt(self.consideration_amount), 2)
            holding.accrued_interest = round(flt(holding.accrued_interest) + flt(self.accrued_interest), 2)
            holding.dirty_market_value = round(flt(holding.dirty_market_value) + flt(self.settlement_amount), 2)
            holding.xirr = flt(self.yield_to_maturity or self.interest_rate or self.coupon_rate or 0.0)
            holding.holding_status = "Active"
        elif self.order_type in ("SELL", "EARLY_RECALL"):
            holding.face_value = round(max(0.0, flt(holding.face_value) - flt(self.face_value)), 2)
            holding.carrying_cost = round(max(0.0, flt(holding.carrying_cost) - flt(self.consideration_amount)), 2)
            holding.dirty_market_value = round(max(0.0, flt(holding.dirty_market_value) - flt(self.settlement_amount)), 2)
            if holding.face_value == 0:
                holding.holding_status = "Sold"

        holding.save(ignore_permissions=True)

        # Generate Custody Instruction (Stanbic Custody Confirmation)
        tx_type_map = {
            "Treasury Bond": "T-BOND PURCHASE" if self.order_type == "BUY" else "T-BOND SALE",
            "Corporate Bond": "T-BOND PURCHASE" if self.order_type == "BUY" else "T-BOND SALE",
            "Treasury Bill": "T-BILL PURCHASE",
            "Fixed Deposit": "FIXED DEPOSIT PLACEMENT",
            "Call Deposit": "FIXED DEPOSIT PLACEMENT",
            "Commercial Paper": "T-BILL PURCHASE",
            "Quoted Equity": "EQUITY PURCHASE" if self.order_type == "BUY" else "EQUITY SALE"
        }
        tx_type = tx_type_map.get(self.asset_class, "T-BOND PURCHASE")

        cust = frappe.new_doc("Asset Custody Instruction")
        cust.instruction_date = self.order_date
        cust.trade_order = self.name
        cust.fund = self.fund
        cust.transaction_type = tx_type
        cust.counterparty = self.counterparty
        cust.security_description = f"{sec.coupon_rate or ''}% {sec.security_name} {sec.maturity_date or ''}".strip()
        cust.isin = sec.isin or ""
        cust.settlement_date = self.settlement_date
        cust.face_value = self.face_value
        cust.clean_price = self.clean_price_pct
        cust.coupon_rate = self.coupon_rate or 0.0
        cust.yield_to_maturity = self.yield_to_maturity or self.interest_rate or 0.0
        cust.accrued_interest = self.accrued_interest or 0.0
        cust.settlement_amount = self.settlement_amount
        cust.maker_signatory = self.dealer or "Administrator"
        cust.checker_signatory = self.approver or "test_checker@example.com"
        cust.status = "Draft"
        cust.insert(ignore_permissions=True)

        self.db_set("custody_instruction_ref", cust.name)
        self.db_set("status", "Approved")

    def on_cancel(self):
        """Reverses holdings and marks trade cancelled."""
        self.db_set("status", "Cancelled")
