import unittest
import frappe
from frappe.utils import flt, today
from frappe.website.serve import get_response_content
from asset_management.asset_management.portal_api import (
    get_resolved_investor,
    get_resolved_agent,
    get_investor_dashboard,
    get_investor_holdings,
    get_investor_statement,
    submit_online_subscription,
    submit_online_redemption,
    get_agent_dashboard
)

class TestSprint6PortalsWorkspaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        # Ensure test investor and fund portfolio exist
        cls.investor_name = "__TEST_INV_S6_01"
        if not frappe.db.exists("Asset Investor", cls.investor_name):
            inv = frappe.new_doc("Asset Investor")
            inv.name = cls.investor_name
            inv.investor_id = cls.investor_name
            inv.investor_name = "Global Alpha Ventures S6"
            inv.investor_type = "Corporate"
            inv.status = "Active"
            inv.risk_tier = "Medium"
            inv.email = "alpha.s6@example.com"
            inv.phone = "+256700112233"
            inv.tax_id = "TIN-S6-ALPHA"
            inv.country_of_residence = "Uganda"
            inv.bank_name = "Stanbic Bank Uganda"
            inv.bank_account_no = "903001889901"
            inv.bank_account_name = "Global Alpha Ventures S6"
            inv.insert(ignore_permissions=True)

        cls.fund_id = "SBG-MMF"

        # Ensure portfolio exists
        cls.portfolio_name = f"{cls.investor_name}-{cls.fund_id}"
        if not frappe.db.exists("Asset Investor Portfolio", cls.portfolio_name):
            pf = frappe.new_doc("Asset Investor Portfolio")
            pf.name = cls.portfolio_name
            pf.investor = cls.investor_name
            pf.fund = cls.fund_id
            pf.portfolio_status = "Active"
            pf.total_units = 10000.0
            pf.current_nav_per_unit = 105.0000
            pf.current_market_value = 1050000.00
            pf.total_invested_amount = 1000000.00
            pf.total_withdrawn_amount = 0.0
            pf.unrealized_gain_loss = 50000.00
            pf.insert(ignore_permissions=True)

        # Ensure register line exists for statement testing
        if not frappe.db.exists("Asset Investor Register Line", {"investor": cls.investor_name}):
            reg = frappe.new_doc("Asset Investor Register Line")
            reg.posting_date = today()
            reg.value_date = today()
            reg.investor = cls.investor_name
            reg.portfolio = cls.portfolio_name
            reg.fund = cls.fund_id
            reg.entry_type = "Subscription"
            reg.voucher_type = "Asset Subscription"
            reg.voucher_no = "SUB-S6-INIT"
            reg.units = 10000.0
            reg.nav_per_unit = 100.0
            reg.running_unit_balance = 10000.0
            reg.gross_amount = 1000000.0
            reg.net_amount = 1000000.0
            reg.insert(ignore_permissions=True)

        # Ensure test agent exists
        cls.agent_code = "AGT-001"
        if not frappe.db.exists("Asset Agent", {"agent_code": cls.agent_code}):
            ag = frappe.new_doc("Asset Agent")
            ag.agent_code = cls.agent_code
            ag.agent_name = "Standard Agency Intermediary"
            ag.agent_type = "Corporate Agent"
            ag.commission_rate_pct = 0.50
            ag.status = "Active"
            ag.email = "agent001@example.com"
            ag.phone = "+256701999888"
            ag.insert(ignore_permissions=True)

        frappe.db.commit()

    def test_01_workspaces_created(self):
        """Verify all 6 desks and workspaces exist in the DB with correct module and app"""
        expected_workspaces = [
            "Asset Management",
            "Asset Operations",
            "Asset Portfolio & Trading",
            "Asset Fund Administration",
            "Asset Compliance & Risk",
            "Asset Client Service"
        ]
        for ws_name in expected_workspaces:
            self.assertTrue(frappe.db.exists("Workspace", ws_name), f"Workspace '{ws_name}' should exist")
            ws = frappe.get_doc("Workspace", ws_name)
            self.assertEqual(ws.type, "Workspace")
            self.assertEqual(ws.module, "Asset Management")
            self.assertEqual(ws.app, "asset_management")
            self.assertEqual(ws.public, 1)

    def test_02_workspace_sidebar_configured(self):
        """Verify Workspace Sidebar 'Asset Management' exists with structured sections and links"""
        self.assertTrue(frappe.db.exists("Workspace Sidebar", "Asset Management"))
        sb = frappe.get_doc("Workspace Sidebar", "Asset Management")
        self.assertEqual(sb.app, "asset_management")
        self.assertEqual(sb.header_icon, "briefcase")

        labels = [item.label for item in sb.items]
        # Check desk links
        self.assertIn("Department Desks", labels)
        self.assertIn("Operations Desk", labels)
        self.assertIn("Portfolio & Trading", labels)
        self.assertIn("Fund Administration", labels)
        self.assertIn("Compliance & Risk", labels)
        self.assertIn("Client Service CRM", labels)
        # Check transaction links
        self.assertIn("Transactions & Orders", labels)
        self.assertIn("Subscriptions", labels)
        self.assertIn("Redemptions (Rule 1)", labels)
        self.assertIn("Trade Orders (Dealer Pot)", labels)

    def test_03_desktop_icon_configured(self):
        """Verify Desktop Icon 'Asset Management' links to sidebar and contains authorized roles"""
        self.assertTrue(frappe.db.exists("Desktop Icon", "Asset Management"))
        di = frappe.get_doc("Desktop Icon", "Asset Management")
        self.assertEqual(di.link_type, "Workspace Sidebar")
        self.assertEqual(di.link_to, "Asset Management")
        self.assertEqual(di.standard, 1)
        role_names = [r.role for r in di.roles]
        self.assertIn("Asset Management Admin", role_names)
        self.assertIn("Asset Management Operations", role_names)
        self.assertIn("Asset Investment Manager", role_names)

    def test_04_investor_dashboard_context(self):
        """Verify get_investor_dashboard returns complete dataset with metrics and portfolios"""
        data = get_investor_dashboard(self.investor_name)
        self.assertNotIn("error", data)
        self.assertIn("investor", data)
        self.assertEqual(data["investor"]["name"], self.investor_name)
        self.assertGreater(data["total_value"], 0)
        self.assertGreater(data["total_units"], 0)
        self.assertIn("portfolios", data)
        self.assertIn("market_funds", data)

    def test_05_investor_holdings_context(self):
        """Verify get_investor_holdings computes average costs and gain percentages"""
        data = get_investor_holdings(self.investor_name)
        self.assertNotIn("error", data)
        self.assertIn("portfolios", data)
        self.assertTrue(len(data["portfolios"]) > 0)
        p = data["portfolios"][0]
        self.assertIn("avg_cost", p)
        self.assertIn("gain_pct", p)
        self.assertGreaterEqual(p["avg_cost"], 0)

    def test_06_investor_statement_ledger(self):
        """Verify get_investor_statement retrieves transaction lines from ledger"""
        data = get_investor_statement(self.investor_name, fund=self.fund_id)
        self.assertNotIn("error", data)
        self.assertIn("lines", data)
        self.assertTrue(len(data["lines"]) > 0)
        first_line = data["lines"][0]
        self.assertEqual(first_line["fund"], self.fund_id)
        self.assertGreater(first_line["units"], 0)

    def test_07_online_subscription_submission(self):
        """Verify submit_online_subscription stages draft subscription request"""
        result = submit_online_subscription(
            investor=self.investor_name,
            fund=self.fund_id,
            amount=250000,
            payment_reference="TEST-S6-SUB-01",
            payment_mode="Bank Transfer / BOL"
        )
        self.assertTrue(result.get("success"))
        sub_name = result.get("subscription")
        self.assertTrue(frappe.db.exists("Asset Subscription", sub_name))
        sub = frappe.get_doc("Asset Subscription", sub_name)
        self.assertEqual(sub.investor, self.investor_name)
        self.assertEqual(sub.fund, self.fund_id)
        self.assertEqual(flt(sub.gross_amount), 250000.0)
        self.assertEqual(sub.docstatus, 0) # Draft

    def test_08_online_redemption_rule1_enforcement(self):
        """Verify submit_online_redemption enforces Foundational Rule 1 (Valuation Guard)"""
        # Ensure fund valuation approval is 0
        fund_doc = frappe.get_doc("Asset Fund", self.fund_id)
        fund_doc.prior_day_valuation_approved = 0
        fund_doc.save(ignore_permissions=True)
        frappe.clear_document_cache("Asset Fund", self.fund_id)
        frappe.db.commit()

        # Attempt redemption -> should raise Rule 1 violation
        with self.assertRaises(frappe.ValidationError):
            submit_online_redemption(
                investor=self.investor_name,
                fund=self.fund_id,
                redemption_by="Units",
                requested_units=100
            )

        # Approve prior-day valuation
        fund_doc.reload()
        fund_doc.prior_day_valuation_approved = 1
        fund_doc.save(ignore_permissions=True)
        frappe.clear_document_cache("Asset Fund", self.fund_id)
        frappe.db.commit()

        # Now redemption should stage successfully
        res = submit_online_redemption(
            investor=self.investor_name,
            fund=self.fund_id,
            redemption_by="Units",
            requested_units=1000
        )
        self.assertTrue(res.get("success"))
        red_name = res.get("redemption")
        self.assertTrue(frappe.db.exists("Asset Redemption", red_name))
        red = frappe.get_doc("Asset Redemption", red_name)
        self.assertEqual(red.investor, self.investor_name)
        self.assertEqual(red.docstatus, 0) # Draft

    def test_09_agent_portal_dashboard(self):
        """Verify get_agent_dashboard calculates commissions and client summaries"""
        data = get_agent_dashboard(self.agent_code)
        self.assertNotIn("error", data)
        self.assertIn("agent", data)
        self.assertEqual(data["agent"]["agent_code"], self.agent_code)
        self.assertIn("total_commission_earned", data)
        self.assertIn("commission_due", data)
        self.assertIn("clients", data)
        self.assertIn("commissions", data)

    def test_10_portal_web_routes_render(self):
        """Verify all 6 portal web endpoints render without HTTP or template errors"""
        routes = [
            ("asset_portal/dashboard", {"investor": self.investor_name}),
            ("asset_portal/holdings", {"investor": self.investor_name}),
            ("asset_portal/statement", {"investor": self.investor_name}),
            ("asset_portal/subscribe", {"investor": self.investor_name}),
            ("asset_portal/redeem", {"investor": self.investor_name}),
            ("agent_portal/dashboard", {"agent": self.agent_code})
        ]

        for path, params in routes:
            frappe.form_dict.clear()
            for k, v in params.items():
                frappe.form_dict[k] = v

            content = get_response_content(path)
            self.assertIsNotNone(content, f"Route {path} should return content")
            self.assertGreater(len(content), 500, f"Route {path} should have non-trivial HTML body")
            has_branding = ("STANBIC ASSET MANAGEMENT" in content) or ("Stanbic Asset Management" in content)
            self.assertTrue(has_branding, f"Route {path} should contain Stanbic branding")

if __name__ == "__main__":
    frappe.init(site="erp.site.com")
    frappe.connect()
    unittest.main()
