"""Integration tests for investor and agent portal APIs and web routes (Sprint 6)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt
from frappe.website.serve import get_response_content

from asset_management.asset_management.portal_api import (
	get_agent_dashboard,
	get_investor_dashboard,
	get_investor_holdings,
	get_investor_statement,
	submit_online_redemption,
	submit_online_subscription,
)
from asset_management.tests.factories import (
	make_agent,
	make_checker_user,
	make_fund,
	make_investor,
	make_subscription,
)


class TestSprint6PortalsWorkspaces(IntegrationTestCase):
	def setUp(self) -> None:
		super().setUp()
		frappe.set_user("Administrator")
		self.checker = make_checker_user("test_checker@example.com")

		self.fund_doc = make_fund(
			fund_id="TEST-S6-MMF",
			fund_name="Test S6 Money Market Fund",
			fund_type="Money Market Fund",
			nav=100.0,
			bid=100.0,
			offer=100.0,
		)
		self.fund_id = self.fund_doc.name

		self.inv_doc = make_investor(
			investor_id="__TEST_INV_S6_01",
			investor_name="Global Alpha Ventures S6",
			investor_type="Corporate",
		)
		self.investor_name = self.inv_doc.name

		self.agent_doc = make_agent(
			agent_code="AGT-S6-001",
			agent_name="Standard Agency Intermediary",
			commission_rate_pct=0.50,
		)
		self.agent_code = self.agent_doc.name

		if not frappe.db.exists(
			"Asset Subscription",
			{"investor": self.investor_name, "fund": self.fund_id, "docstatus": 1},
		):
			make_subscription(
				investor=self.investor_name,
				fund=self.fund_id,
				amount=1_000_000.0,
				agent=self.agent_code,
				checker_user=self.checker,
			)

	def test_04_investor_dashboard_context(self) -> None:
		"""Verify get_investor_dashboard returns complete dataset with metrics and portfolios."""
		data = get_investor_dashboard(self.investor_name)
		self.assertNotIn("error", data)
		self.assertIn("investor", data)
		self.assertEqual(data["investor"]["name"], self.investor_name)
		self.assertGreater(data["total_value"], 0)
		self.assertGreater(data["total_units"], 0)
		self.assertIn("portfolios", data)
		self.assertIn("market_funds", data)

	def test_05_investor_holdings_context(self) -> None:
		"""Verify get_investor_holdings computes average costs and gain percentages."""
		data = get_investor_holdings(self.investor_name)
		self.assertNotIn("error", data)
		self.assertIn("portfolios", data)
		self.assertGreater(len(data["portfolios"]), 0)
		p = data["portfolios"][0]
		self.assertIn("avg_cost", p)
		self.assertIn("gain_pct", p)
		self.assertGreaterEqual(p["avg_cost"], 0)

	def test_06_investor_statement_ledger(self) -> None:
		"""Verify get_investor_statement retrieves transaction lines from ledger."""
		data = get_investor_statement(self.investor_name, fund=self.fund_id)
		self.assertNotIn("error", data)
		self.assertIn("lines", data)
		self.assertGreater(len(data["lines"]), 0)
		first_line = data["lines"][0]
		self.assertEqual(first_line["fund"], self.fund_id)
		self.assertGreater(first_line["units"], 0)

	def test_07_online_subscription_submission(self) -> None:
		"""Verify submit_online_subscription stages draft subscription request."""
		result = submit_online_subscription(
			investor=self.investor_name,
			fund=self.fund_id,
			amount=250000,
			payment_reference="TEST-S6-SUB-01",
			payment_mode="Bank Transfer / BOL",
		)
		self.assertTrue(result.get("success"))
		sub_name = result.get("subscription")
		self.assertTrue(frappe.db.exists("Asset Subscription", sub_name))
		sub = frappe.get_doc("Asset Subscription", sub_name)
		self.assertEqual(sub.investor, self.investor_name)
		self.assertEqual(sub.fund, self.fund_id)
		self.assertEqual(flt(sub.gross_amount), 250000.0)
		self.assertEqual(sub.docstatus, 0)

	def test_08_online_redemption_rule1_enforcement(self) -> None:
		"""Verify submit_online_redemption enforces Foundational Rule 1 (Valuation Guard)."""
		fund_doc = frappe.get_doc("Asset Fund", self.fund_id)
		fund_doc.prior_day_valuation_approved = 0
		# Test setup: ignore_permissions required
		fund_doc.save(ignore_permissions=True)
		frappe.clear_document_cache("Asset Fund", self.fund_id)

		with self.assertRaises(frappe.ValidationError):
			submit_online_redemption(
				investor=self.investor_name,
				fund=self.fund_id,
				redemption_by="Units",
				requested_units=100,
			)

		fund_doc.reload()
		fund_doc.prior_day_valuation_approved = 1
		# Test setup: ignore_permissions required
		fund_doc.save(ignore_permissions=True)
		frappe.clear_document_cache("Asset Fund", self.fund_id)

		res = submit_online_redemption(
			investor=self.investor_name,
			fund=self.fund_id,
			redemption_by="Units",
			requested_units=1000,
		)
		self.assertTrue(res.get("success"))
		red_name = res.get("redemption")
		self.assertTrue(frappe.db.exists("Asset Redemption", red_name))
		red = frappe.get_doc("Asset Redemption", red_name)
		self.assertEqual(red.investor, self.investor_name)
		self.assertEqual(red.docstatus, 0)

	def test_09_agent_portal_dashboard(self) -> None:
		"""Verify get_agent_dashboard calculates commissions and client summaries."""
		data = get_agent_dashboard(self.agent_code)
		self.assertNotIn("error", data)
		self.assertIn("agent", data)
		self.assertEqual(data["agent"]["agent_code"], self.agent_code)
		self.assertEqual(flt(data["total_commission_earned"]), 5000.0)
		self.assertIn("commission_due", data)
		self.assertIn("clients", data)
		self.assertIn("commissions", data)

	def test_10_portal_web_routes_render(self) -> None:
		"""Verify all 6 portal web endpoints render without HTTP or template errors."""
		routes = [
			("asset_portal/dashboard", {"investor": self.investor_name}),
			("asset_portal/holdings", {"investor": self.investor_name}),
			("asset_portal/statement", {"investor": self.investor_name}),
			("asset_portal/subscribe", {"investor": self.investor_name}),
			("asset_portal/redeem", {"investor": self.investor_name}),
			("agent_portal/dashboard", {"agent": self.agent_code}),
		]

		for path, params in routes:
			frappe.form_dict.clear()
			for k, v in params.items():
				frappe.form_dict[k] = v

			content = get_response_content(path)
			self.assertIsNotNone(content, f"Route {path} should return content")
			self.assertGreater(len(content), 500, f"Route {path} should have non-trivial HTML body")
			has_branding = ("ASSET MANAGEMENT" in content) or ("Asset Management" in content)
			self.assertTrue(has_branding, f"Route {path} should contain Asset Management branding")
