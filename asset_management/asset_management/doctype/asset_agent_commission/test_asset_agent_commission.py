"""Integration tests for Asset Agent Commission DocType."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from asset_management.tests.factories import (
	make_agent,
	make_checker_user,
	make_fund,
	make_investor,
	make_subscription,
)

IGNORE_TEST_RECORD_DEPENDENCIES = ["User", "Company", "Account", "Supplier"]


class IntegrationTestAssetAgentCommission(IntegrationTestCase):
	def test_commission_accrued_on_subscription_and_cancelled_on_reversal(self) -> None:
		checker = make_checker_user()
		fund = make_fund(fund_id="TEST-COMM-MMF", nav=100.0)
		inv = make_investor()
		agent = make_agent(agent_code="AGT-COMM-01", commission_rate_pct=1.0)

		sub = make_subscription(
			investor=inv.name,
			fund=fund.name,
			amount=500000.0,
			agent=agent.name,
			checker_user=checker,
		)

		comm = frappe.get_doc("Asset Agent Commission", {"subscription": sub.name})
		self.assertEqual(comm.agent, agent.name)
		self.assertEqual(flt(comm.commission_amount, 2), 5000.0)
		self.assertEqual(comm.payment_status, "Accrued")

		sub.reload()
		sub.cancel()
		comm.reload()
		self.assertEqual(comm.payment_status, "Cancelled")
