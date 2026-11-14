"""Brand-neutrality scan and demo setup tests (Task R-03).

Ensures no client brand names or country/currency hardcodings exist in the app
outside this test file itself, and verifies asset_management.demo.setup_demo.run().
"""

import re
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from asset_management.demo.setup_demo import run as run_setup_demo

BANNED_WORDS = (
	"SBG",
	"Stanbic",
	"Uganda",
	"URA",
	"Bank of Uganda",
	"MTN",
	"UGX",
	"CMA",
)

SCAN_EXTENSIONS = {".py", ".js", ".json", ".html", ".md"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".ruff_cache", ".pytest_cache"}


class TestNoClientBrands(IntegrationTestCase):
	"""Scans all source, fixture, template, and markdown files for banned brand terms."""

	def test_no_banned_client_brands_in_app_files(self) -> None:
		app_root = Path(frappe.get_app_path("asset_management")).resolve().parent
		this_file = Path(__file__).resolve()

		# Match acronyms case-sensitively (including inside underscores like SBG_MMF) and names case-insensitively
		pattern = re.compile(r"SBG|URA|MTN|UGX|CMA|(?i:Stanbic|Uganda|Bank of Uganda)")

		hits: list[str] = []
		for path in sorted(app_root.rglob("*")):
			if not path.is_file():
				continue
			if any(part in SKIP_DIRS for part in path.parts):
				continue
			if path.suffix not in SCAN_EXTENSIONS:
				continue
			if path.resolve() == this_file:
				continue

			text = path.read_text(encoding="utf-8", errors="ignore")
			for lineno, line in enumerate(text.splitlines(), start=1):
				match = pattern.search(line)
				if match:
					rel_path = path.relative_to(app_root)
					hits.append(f"{rel_path}:{lineno}: matched '{match.group(0)}' -> {line.strip()[:100]}")

		self.assertEqual(
			hits,
			[],
			"Found banned client/country brand strings in app files:\n" + "\n".join(hits[:50]),
		)

	def test_setup_demo_is_idempotent_and_creates_neutral_records(self) -> None:
		result1 = run_setup_demo()
		self.assertEqual(result1["fund_manager_company"], "Demo Fund Manager")
		self.assertIn("DEMO-MMF", result1["funds"])
		self.assertIn("DEMO-BAL", result1["funds"])
		self.assertEqual(len(result1["agents"]), 2)
		self.assertEqual(len(result1["securities"]), 5)

		# Verify each demo fund has its own isolated Company and accounts provisioned
		mmf = frappe.get_doc("Asset Fund", "DEMO-MMF")
		bal = frappe.get_doc("Asset Fund", "DEMO-BAL")
		self.assertEqual(mmf.fund_name, "Demo Money Market Fund")
		self.assertEqual(bal.fund_name, "Demo Balanced Fund")
		self.assertTrue(bool(mmf.company))
		self.assertTrue(bool(bal.company))
		self.assertNotEqual(mmf.company, bal.company)
		self.assertNotEqual(mmf.company, "Demo Fund Manager")
		self.assertTrue(bool(mmf.client_cash_payable_account))
		self.assertTrue(bool(bal.unitholders_capital_account))

		# Verify the 5 generic securities exist with neutral names
		expected_sec_names = {
			"Demo Government Bond 2030",
			"Demo Treasury Bill 364D",
			"Demo Bank Fixed Deposit 180D",
			"Demo Listed Equity A",
			"Demo Corporate Bond 2028",
		}
		actual_sec_names = set(
			frappe.get_all(
				"Asset Investment Security",
				filters={"name": ["in", result1["securities"]]},
				pluck="security_name",
			)
		)
		self.assertEqual(actual_sec_names, expected_sec_names)

		# Run a second time to verify idempotency (no duplicates)
		fund_count_before = frappe.db.count("Asset Fund", {"name": ["in", ["DEMO-MMF", "DEMO-BAL"]]})
		sec_count_before = frappe.db.count(
			"Asset Investment Security", {"name": ["in", result1["securities"]]}
		)
		result2 = run_setup_demo()
		self.assertEqual(result1, result2)
		self.assertEqual(
			frappe.db.count("Asset Fund", {"name": ["in", ["DEMO-MMF", "DEMO-BAL"]]}),
			fund_count_before,
		)
		self.assertEqual(
			frappe.db.count("Asset Investment Security", {"name": ["in", result1["securities"]]}),
			sec_count_before,
		)
