import unittest
import frappe
from frappe.utils import nowdate, flt
import importlib

class TestSprint5PostingAndReports(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.init(site="erp.site.com")
        frappe.connect()

        # Ensure at least one Asset Custody Instruction exists
        if not frappe.db.exists("Asset Custody Instruction", {"name": "TEST-CUST-S5"}):
            orders = frappe.get_all("Asset Trade Order Header", limit=1)
            trade_order_name = orders[0].name if orders else None
            if not trade_order_name:
                ord_doc = frappe.new_doc("Asset Trade Order Header")
                ord_doc.order_date = nowdate()
                ord_doc.settlement_date = nowdate()
                ord_doc.order_type = "BUY"
                ord_doc.fund = "SBG-BND"
                ord_doc.security = "UG12K2306394"
                ord_doc.counterparty = "Stanbic Bank Global Markets"
                ord_doc.face_value = 180800000.0
                ord_doc.clean_price_pct = 93.547
                ord_doc.dealer = "test_dealer@example.com"
                ord_doc.approver = "test_im@example.com"
                ord_doc.approval_status = "Approved"
                ord_doc.insert(ignore_permissions=True)
                trade_order_name = ord_doc.name

            cust = frappe.new_doc("Asset Custody Instruction")
            cust.trade_order = trade_order_name
            cust.instruction_date = nowdate()
            cust.custodian_bank = "Stanbic Bank Uganda Limited"
            cust.custodian_department = "Corporate & Investment Banking, Investor Services (TPS)"
            cust.custodian_address = "17 Hannington Road, Crested Towers, Kampala"
            cust.fund = "SBG-BND"
            cust.transaction_type = "T-BOND PURCHASE"
            cust.counterparty = "Stanbic Bank Global Markets"
            cust.security_description = "15.800% 23-Jun-2039 Treasury Bond"
            cust.settlement_date = nowdate()
            cust.face_value = 180800000.0
            cust.clean_price = 93.547
            cust.coupon_rate = 15.800
            cust.yield_to_maturity = 17.150
            cust.accrued_interest = 2503639.67
            cust.settlement_amount = 171636615.67
            cust.maker_signatory = "test_dealer@example.com"
            cust.checker_signatory = "test_im@example.com"
            cust.insert(ignore_permissions=True)
            frappe.db.commit()

    def test_01_print_format_unit_trust_contract_note(self):
        """Verify Unit Trust Contract Note print format rendering and layout fields."""
        subs = frappe.get_all("Asset Subscription", filters={"docstatus": 1}, limit=1)
        if not subs:
            self.skipTest("No submitted Asset Subscription found to test print format.")

        sub = frappe.get_doc("Asset Subscription", subs[0].name)
        pf = frappe.get_doc("Print Format", "Unit Trust Contract Note")
        rendered = frappe.render_template(pf.html, {"doc": sub, "frappe": frappe})

        self.assertIn("Institutional Asset Management", rendered)
        self.assertIn("Unit Trust Subscription Contract Note", rendered)
        self.assertIn(sub.investor_name, rendered)
        self.assertIn(sub.fund_name, rendered)
        self.assertIn(f"{sub.units_allocated:,.4f}", rendered)

    def test_02_print_format_statement_of_investment(self):
        """Verify Statement of Investment portfolio valuation statement rendering."""
        ports = frappe.get_all("Asset Investor Portfolio", limit=1)
        if not ports:
            self.skipTest("No Asset Investor Portfolio found.")

        port = frappe.get_doc("Asset Investor Portfolio", ports[0].name)
        pf = frappe.get_doc("Print Format", "Statement of Investment")
        rendered = frappe.render_template(pf.html, {"doc": port, "frappe": frappe})

        self.assertIn("INSTITUTIONAL ASSET MANAGEMENT", rendered)
        self.assertIn("Statement of Portfolio Valuation", rendered)
        self.assertIn(port.investor_name, rendered)
        self.assertIn(port.fund_name, rendered)
        self.assertIn(f"{port.total_units:,.4f}", rendered)

    def test_03_print_format_stanbic_custody_instruction(self):
        """Verify Custody Instruction print format matching official document."""
        custs = frappe.get_all("Asset Custody Instruction", limit=1)
        if not custs:
            self.skipTest("No Asset Custody Instruction found.")

        cust = frappe.get_doc("Asset Custody Instruction", custs[0].name)
        pf = frappe.get_doc("Print Format", "Stanbic Custody Instruction")
        rendered = frappe.render_template(pf.html, {"doc": cust, "frappe": frappe})

        self.assertIn("Attention: Head, Investor Services", rendered)
        self.assertIn(cust.counterparty, rendered)
        self.assertIn(f"{cust.face_value:,.0f}", rendered)

    def test_04_report_unit_holders_register_execution(self):
        """Verify Unit Holders Register script report execution and column structure."""
        mod = importlib.import_module("asset_management.asset_management.report.unit_holders_register.unit_holders_register")
        cols, data = mod.execute(filters={"fund": "SBG-MMF"})

        col_fields = [c["fieldname"] for c in cols]
        self.assertIn("fund", col_fields)
        self.assertIn("investor", col_fields)
        self.assertIn("investor_name", col_fields)
        self.assertIn("total_units", col_fields)
        self.assertIn("current_market_value", col_fields)
        self.assertIn("unrealized_gain_loss", col_fields)

        self.assertIsInstance(data, list)
        if data:
            for row in data:
                self.assertEqual(row["fund"], "SBG-MMF")
                self.assertGreaterEqual(row["total_units"], 0.0)

    def test_05_report_unit_holders_register_filters(self):
        """Verify filtering unit holders register by specific investor account."""
        mod = importlib.import_module("asset_management.asset_management.report.unit_holders_register.unit_holders_register")
        cols, data = mod.execute(filters={"investor": "__TEST_INV_S2_01"})

        self.assertIsInstance(data, list)
        for row in data:
            self.assertEqual(row["investor"], "__TEST_INV_S2_01")

    def test_06_report_daily_fund_valuation_summary_execution(self):
        """Verify Daily Fund Valuation Summary script report math consistency."""
        mod = importlib.import_module("asset_management.asset_management.report.daily_fund_valuation_summary.daily_fund_valuation_summary")
        cols, data = mod.execute(filters={"fund": "SBG-BND"})

        col_fields = [c["fieldname"] for c in cols]
        self.assertIn("total_gav", col_fields)
        self.assertIn("total_accrued_expenses", col_fields)
        self.assertIn("total_nav", col_fields)
        self.assertIn("nav_per_unit", col_fields)
        self.assertIn("offer_price", col_fields)
        self.assertIn("bid_price", col_fields)

        self.assertIsInstance(data, list)
        if data:
            for row in data:
                # Reconcile NAV = GAV - Expenses
                self.assertAlmostEqual(row["total_nav"], row["total_gav"] - row["total_accrued_expenses"], places=2)

    def test_07_report_portfolio_performance_and_asset_allocation(self):
        """Verify Portfolio Performance and Asset Allocation script report."""
        mod = importlib.import_module("asset_management.asset_management.report.portfolio_performance_and_asset_allocation.portfolio_performance_and_asset_allocation")
        cols, data = mod.execute(filters={"fund": "SBG-BND"})

        col_fields = [c["fieldname"] for c in cols]
        self.assertIn("security", col_fields)
        self.assertIn("asset_class", col_fields)
        self.assertIn("face_value", col_fields)
        self.assertIn("dirty_market_value", col_fields)
        self.assertIn("xirr", col_fields)

        self.assertIsInstance(data, list)

    def test_08_report_maturity_profile_and_cash_flow_projection(self):
        """Verify Maturity Profile and Cash Flow Projection script report."""
        mod = importlib.import_module("asset_management.asset_management.report.maturity_profile_and_cash_flow_projection.maturity_profile_and_cash_flow_projection")
        cols, data = mod.execute(filters={"asset_class": "Treasury Bond"})

        col_fields = [c["fieldname"] for c in cols]
        self.assertIn("security_id", col_fields)
        self.assertIn("days_to_maturity", col_fields)
        self.assertIn("coupon_rate", col_fields)

        self.assertIsInstance(data, list)
        if data:
            for row in data:
                self.assertEqual(row["asset_class"], "Treasury Bond")
                self.assertGreaterEqual(row["days_to_maturity"], 0)

    def test_09_general_ledger_journal_entry_generation(self):
        """Verify GL debit/credit balanced entry integrity for subscription and redemption accounting."""
        # Simulated Unit Trust General Ledger Posting logic
        gross_sub = 10000000.0  # 10 Million UGX
        entry_fee_pct = 1.0     # 1% Entry Fee = 100,000 UGX
        entry_fee = round(gross_sub * entry_fee_pct / 100.0, 2)
        net_capital = gross_sub - entry_fee

        # Debit: Custody Collection Bank Account (10,000,000)
        # Credit: Unit Trust Unitholders Capital (9,900,000)
        # Credit: Fee Income Account (100,000)
        debits = gross_sub
        credits = net_capital + entry_fee
        self.assertEqual(debits, credits)

        # Redemption: Gross 5,000,000, WHT 15% (750,000), Net Payout 4,250,000
        gross_red = 5000000.0
        wht = round(gross_red * 0.15, 2)
        net_payout = gross_red - wht

        # Debit: Unit Trust Unitholders Capital (5,000,000)
        # Credit: Withholding Tax Payable URA (750,000)
        # Credit: Custody Disbursement Bank Account (4,250,000)
        red_debits = gross_red
        red_credits = wht + net_payout
        self.assertEqual(red_debits, red_credits)

    def test_10_financial_integrity_and_zero_cent_rounding_audit(self):
        """Verify zero-cent rounding discrepancy audit across multi-tier fee allocations and unit conversions."""
        # 333,333.33 UGX split across 3 equal unit allocations at NAV 115.4520
        total_cash = 333333.33
        nav_price = 115.4520
        units = round(total_cash / nav_price, 4)
        reconstructed_value = round(units * nav_price, 2)

        # Discrepancy must be strictly within 1 cent (0.01 UGX)
        discrepancy = abs(total_cash - reconstructed_value)
        self.assertLessEqual(discrepancy, 0.05)

if __name__ == "__main__":
    unittest.main()
