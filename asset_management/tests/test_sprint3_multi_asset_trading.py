import unittest
import frappe
from frappe.utils import nowdate, add_days, flt

class TestSprint3MultiAssetTrading(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.init(site="erp.site.com")
        frappe.connect()

        # Clean existing test trade orders and holdings
        frappe.db.delete("Asset Custody Instruction", {"fund": ["in", ["SBG-BND", "SBG-BAL", "SBG-MMF"]]})
        frappe.db.delete("Asset Trade Order Header", {"fund": ["in", ["SBG-BND", "SBG-BAL", "SBG-MMF"]]})
        frappe.db.delete("Asset Portfolio Holding", {"fund": ["in", ["SBG-BND", "SBG-BAL", "SBG-MMF"]]})

        # Ensure test users exist
        if not frappe.db.exists("User", "test_dealer@example.com"):
            u1 = frappe.new_doc("User")
            u1.email = "test_dealer@example.com"
            u1.first_name = "Salima"
            u1.last_name = "Katamba"
            u1.send_welcome_email = 0
            u1.insert(ignore_permissions=True)

        if not frappe.db.exists("User", "test_im@example.com"):
            u2 = frappe.new_doc("User")
            u2.email = "test_im@example.com"
            u2.first_name = "Nakiboneka"
            u2.last_name = "Semakula"
            u2.send_welcome_email = 0
            u2.insert(ignore_permissions=True)

        frappe.db.commit()

    def test_01_security_master_and_auto_coupon_schedule(self):
        """Verify bond security master and automated semi-annual coupon schedule generation."""
        sec = frappe.get_doc("Asset Investment Security", "UG12K2306394")
        self.assertEqual(sec.asset_class, "Treasury Bond")
        self.assertEqual(sec.coupon_rate, 15.800)
        self.assertEqual(sec.coupon_frequency, "Semi-Annual")
        self.assertEqual(sec.day_count_convention, "Actual/365")

        # Verify coupon schedule has been generated
        self.assertGreater(len(sec.coupon_schedule), 10)
        c1 = sec.coupon_schedule[0]
        self.assertEqual(c1.coupon_number, 1)
        self.assertEqual(c1.coupon_rate, 7.90)  # 15.8% / 2

    def test_02_treasury_bond_purchase_clean_dirty_price_calculation(self):
        """Verify T-Bond purchase matching real Stanbic SBU Custody Confirmation deal terms."""
        # Stanbic SBU Deal: Face 180,800,000 UGX, Clean Price 93.547%
        # Consideration = 169,132,976 UGX
        order = frappe.new_doc("Asset Trade Order Header")
        order.order_date = "2025-07-25"
        order.settlement_date = "2025-07-25"
        order.order_type = "BUY"
        order.fund = "SBG-BND"
        order.security = "UG12K2306394"
        order.counterparty = "Stanbic Bank Global Markets"
        order.face_value = 180800000.0
        order.clean_price_pct = 93.547
        order.yield_to_maturity = 17.150
        order.days_accrued = 32
        order.dealer = "test_dealer@example.com"
        order.approver = "test_im@example.com"
        order.approval_status = "Approved"
        order.insert(ignore_permissions=True)

        # Verification of mathematical formulas
        expected_consideration = round(180800000.0 * 0.93547, 2)
        self.assertEqual(order.consideration_amount, 169132976.0)
        self.assertAlmostEqual(order.consideration_amount, expected_consideration, places=2)

        expected_accrued = round(180800000.0 * 0.158 * 32 / 365.0, 2)
        self.assertAlmostEqual(order.accrued_interest, expected_accrued, places=2)

        expected_settlement = round(order.consideration_amount + order.accrued_interest, 2)
        self.assertEqual(order.settlement_amount, expected_settlement)
        self.assertGreater(order.dirty_price, order.clean_price_pct)

    def test_03_treasury_bill_discount_basis(self):
        """Verify Treasury Bill trade on discount basis."""
        order = frappe.new_doc("Asset Trade Order Header")
        order.order_date = nowdate()
        order.settlement_date = nowdate()
        order.order_type = "BUY"
        order.fund = "SBG-MMF"
        order.security = "TBILL-364D-2027"
        order.counterparty = "Bank of Uganda Primary Auction"
        order.face_value = 500000000.0
        order.clean_price_pct = 88.100  # Discounted price
        order.yield_to_maturity = 13.50
        order.dealer = "test_dealer@example.com"
        order.approver = "test_im@example.com"
        order.approval_status = "Approved"
        order.insert(ignore_permissions=True)

        expected_settlement = round(500000000.0 * 0.881, 2)
        self.assertEqual(order.consideration_amount, expected_settlement)
        self.assertEqual(order.settlement_amount, 440500000.0)
        self.assertEqual(order.accrued_interest, 0.0)

    def test_04_fixed_deposit_placement_accrual_projection(self):
        """Verify Fixed Deposit placement and interest maturity calculation."""
        order = frappe.new_doc("Asset Trade Order Header")
        order.order_date = nowdate()
        order.settlement_date = nowdate()
        order.order_type = "PLACEMENT"
        order.fund = "SBG-MMF"
        order.security = "FD-STANBIC-180D"
        order.counterparty = "Stanbic Bank Uganda Treasury"
        order.face_value = 1000000000.0
        order.deposit_tenor_days = 180
        order.interest_rate = 12.0
        order.dealer = "test_dealer@example.com"
        order.approver = "test_im@example.com"
        order.approval_status = "Approved"
        order.insert(ignore_permissions=True)

        self.assertEqual(order.consideration_amount, 1000000000.0)
        self.assertEqual(order.settlement_amount, 1000000000.0)
        # 1B * 12% * 180 / 365 = 59,178,082.19 UGX
        expected_interest = round(1000000000.0 * 0.12 * 180 / 365.0, 2)
        self.assertAlmostEqual(order.expected_interest, expected_interest, places=2)
        self.assertEqual(order.maturity_date, add_days(order.order_date, 180))

    def test_05_quoted_equity_trade_calculation(self):
        """Verify Quoted Equity trade consideration and brokerage fee settlement."""
        order = frappe.new_doc("Asset Trade Order Header")
        order.order_date = nowdate()
        order.settlement_date = add_days(nowdate(), 3)  # T+3 settlement
        order.order_type = "BUY"
        order.fund = "SBG-BAL"
        order.security = "EQ-MTNU"
        order.counterparty = "USE Secondary Market"
        order.face_value = 500000.0  # 500,000 shares
        order.clean_price_pct = 240.0  # 240 UGX / share
        order.brokerage_commission = 1200000.0  # 1% brokerage
        order.dealer = "test_dealer@example.com"
        order.approver = "test_im@example.com"
        order.approval_status = "Approved"
        order.insert(ignore_permissions=True)

        self.assertEqual(order.consideration_amount, 120000000.0)
        self.assertEqual(order.settlement_amount, 121200000.0)

    def test_06_pre_trade_compliance_cash_overdraft_block(self):
        """Verify Foundational Rule 2: Trade exceeding available cash triggers compliance breach."""
        order = frappe.new_doc("Asset Trade Order Header")
        order.order_date = nowdate()
        order.settlement_date = nowdate()
        order.order_type = "BUY"
        order.fund = "SBG-MMF"
        order.security = "UG12K2306394"
        order.counterparty = "Stanbic Bank Global Markets"
        order.face_value = 100000000000.0  # 100 Billion UGX (exceeds cash!)
        order.clean_price_pct = 95.0
        order.dealer = "test_dealer@example.com"
        order.approver = "test_im@example.com"
        order.approval_status = "Approved"
        order.insert(ignore_permissions=True)

        self.assertEqual(order.compliance_status, "Breached")
        self.assertIn("Cash Overdraft Breach", order.compliance_notes)

        # Attempt to submit without compliance override -> Must fail!
        with self.assertRaises(frappe.ValidationError):
            order.submit()

    def test_07_pre_trade_compliance_asset_class_limit_check(self):
        """Verify pre-trade compliance checks fund asset allocation limit (30% equity limit on SBG-BAL)."""
        order = frappe.new_doc("Asset Trade Order Header")
        order.order_date = nowdate()
        order.settlement_date = nowdate()
        order.order_type = "BUY"
        order.fund = "SBG-BAL"
        order.security = "EQ-MTNU"
        order.counterparty = "USE Secondary Market"
        # 20M shares at 240 UGX = 4.8 Billion UGX (> 30% of fund AUM)
        order.face_value = 20000000.0
        order.clean_price_pct = 240.0
        order.dealer = "test_dealer@example.com"
        order.approver = "test_im@example.com"
        order.approval_status = "Approved"
        order.insert(ignore_permissions=True)

        self.assertEqual(order.compliance_status, "Breached")
        self.assertIn("Asset Class Limit Breach", order.compliance_notes)

        # Attempt to submit without override -> Must fail!
        with self.assertRaises(frappe.ValidationError):
            order.submit()

    def test_08_compliance_override_and_maker_checker_authorization(self):
        """Verify override justification workflow and maker != checker governance."""
        order = frappe.new_doc("Asset Trade Order Header")
        order.order_date = nowdate()
        order.settlement_date = nowdate()
        order.order_type = "BUY"
        order.fund = "SBG-BAL"
        order.security = "EQ-MTNU"
        order.counterparty = "USE Secondary Market"
        order.face_value = 20000000.0
        order.clean_price_pct = 240.0
        order.dealer = "test_dealer@example.com"
        order.approver = "test_dealer@example.com"  # Maker == Checker!
        order.approval_status = "Approved"
        order.override_approved = 1
        order.override_justification = "IC resolution #44 approved equity overweight."
        order.insert(ignore_permissions=True)

        # Maker == Checker should fail!
        with self.assertRaises(frappe.ValidationError):
            order.submit()

        # Set distinct approver and submit
        order.reload()
        order.approver = "test_im@example.com"
        order.submit()

        self.assertEqual(order.status, "Approved")
        self.assertTrue(bool(order.custody_instruction_ref))

    def test_09_portfolio_holding_ledger_update(self):
        """Verify portfolio holding ledger updates with new position after trade submission."""
        holding_id = "SBG-BAL-EQ-MTNU"
        self.assertTrue(frappe.db.exists("Asset Portfolio Holding", holding_id))
        holding = frappe.get_doc("Asset Portfolio Holding", holding_id)
        self.assertEqual(holding.asset_class, "Quoted Equity")
        self.assertEqual(holding.face_value, 20000000.0)
        self.assertEqual(holding.carrying_cost, 4800000000.0)
        self.assertEqual(holding.holding_status, "Active")

    def test_10_custody_instruction_generation_and_dual_signature_settlement(self):
        """Verify automated custody ticket creation and dual-signature settlement dispatch."""
        # 1. Create and submit trade order
        order = frappe.new_doc("Asset Trade Order Header")
        order.order_date = nowdate()
        order.settlement_date = nowdate()
        order.order_type = "BUY"
        order.fund = "SBG-BND"
        order.security = "UG12K0811352"
        order.counterparty = "Stanbic Bank Global Markets"
        order.face_value = 500000000.0
        order.clean_price_pct = 99.657
        order.yield_to_maturity = 16.900
        order.dealer = "test_dealer@example.com"
        order.approver = "test_im@example.com"
        order.approval_status = "Approved"
        order.insert(ignore_permissions=True)
        order.submit()

        cust_id = order.custody_instruction_ref
        self.assertTrue(bool(cust_id))
        self.assertTrue(frappe.db.exists("Asset Custody Instruction", cust_id))

        cust = frappe.get_doc("Asset Custody Instruction", cust_id)
        self.assertEqual(cust.transaction_type, "T-BOND PURCHASE")
        self.assertEqual(cust.face_value, 500000000.0)
        self.assertEqual(cust.clean_price, 99.657)
        self.assertEqual(cust.custodian_bank, "Stanbic Bank Uganda Limited")

        # 2. Attempt submit with 0 or 1 signature -> Must fail!
        cust.maker_signed = 1
        cust.checker_signed = 0
        with self.assertRaises(frappe.ValidationError):
            cust.submit()

        # 3. Dual signatures -> Authorized & Dispatched -> Marks Trade Order Settled!
        cust.reload()
        cust.maker_signed = 1
        cust.checker_signed = 1
        cust.submit()

        self.assertEqual(cust.status, "Authorized & Dispatched")
        order.reload()
        self.assertEqual(order.status, "Settled")

if __name__ == "__main__":
    unittest.main()
EOF
