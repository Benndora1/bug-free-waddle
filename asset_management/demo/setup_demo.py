"""Idempotent demo data setup command for asset_management.

Execute via:
    bench --site <site> execute asset_management.demo.setup_demo.run
"""

from typing import Any

import frappe
from frappe.utils import nowdate

from asset_management.services.fund_setup import (
	ensure_root_department_exists,
	find_parent_account,
	seed_default_account_templates,
	setup_fund_accounts,
)


def _ensure_fund_manager_company(
	company_name: str = "Demo Fund Manager", currency: str = "USD", country: str = "United States"
) -> str:
	"""Ensures the Demo Fund Manager company and its commission accounts exist."""
	ensure_root_department_exists()
	if not frappe.db.exists("Company", company_name):
		comp = frappe.new_doc("Company")
		comp.company_name = company_name
		abbr = "DFM"
		suffix = 1
		while frappe.db.exists("Company", {"abbr": abbr}):
			abbr = f"DFM{suffix}"
			suffix += 1
		comp.abbr = abbr
		comp.default_currency = currency
		comp.country = country
		comp.chart_of_accounts = "Standard"
		comp.default_payroll_payable_account = None
		# System setup job: ignore_permissions required when executed from CLI
		comp.insert(ignore_permissions=True)

	comp_currency = frappe.db.get_value("Company", company_name, "default_currency") or currency

	exp_acc = frappe.db.get_value(
		"Account", {"company": company_name, "account_name": "Agent Commission Expense"}, "name"
	)
	if not exp_acc:
		parent_exp = find_parent_account(company_name, "Indirect Expenses", "Expense")
		doc = frappe.new_doc("Account")
		doc.account_name = "Agent Commission Expense"
		doc.company = company_name
		doc.parent_account = parent_exp
		doc.root_type = "Expense"
		doc.is_group = 0
		doc.account_currency = comp_currency
		# System setup job: ignore_permissions required
		doc.insert(ignore_permissions=True)
		exp_acc = doc.name

	pay_acc = frappe.db.get_value(
		"Account", {"company": company_name, "account_name": "Agent Commission Payable"}, "name"
	)
	if not pay_acc:
		parent_liab = find_parent_account(company_name, "Current Liabilities", "Liability")
		doc = frappe.new_doc("Account")
		doc.account_name = "Agent Commission Payable"
		doc.company = company_name
		doc.parent_account = parent_liab
		doc.root_type = "Liability"
		doc.account_type = "Payable"
		doc.is_group = 0
		doc.account_currency = comp_currency
		# System setup job: ignore_permissions required
		doc.insert(ignore_permissions=True)
		pay_acc = doc.name

	seed_default_account_templates(backfill_existing=False)
	settings = frappe.get_single("Fund Management Settings")
	settings.fund_manager_company = company_name
	settings.commission_expense_account = exp_acc
	settings.commission_payable_account = pay_acc
	if not settings.regulatory_fee_label:
		settings.regulatory_fee_label = "Regulatory Fee"
	# System setup job: ignore_permissions required
	settings.save(ignore_permissions=True)

	return company_name


def _ensure_demo_funds(currency: str = "USD") -> list[str]:
	"""Creates Demo Money Market Fund and Demo Balanced Fund and provisions their accounts."""
	demo_funds = [
		{
			"fund_id": "DEMO-MMF",
			"fund_name": "Demo Money Market Fund",
			"fund_type": "Money Market Fund",
			"launch_date": "2024-01-01",
			"currency": currency,
			"status": "Active",
			"accounting_basis": "Amortised Cost",
			"initial_nav_per_unit": 100.0,
			"current_nav_per_unit": 108.45,
			"current_bid_price": 108.45,
			"current_offer_price": 108.45,
			"bid_offer_spread_pct": 0.0,
			"prior_day_valuation_approved": 1,
			"last_valuation_date": nowdate(),
			"min_subscription_amount": 100.0,
			"min_additional_amount": 50.0,
			"min_redemption_amount": 50.0,
			"min_balance_amount": 50.0,
			"custodian_name": "Demo Global Custody Services",
			"custodian_account": "CUST-DEMO-001",
			"custodian_address": "100 Financial District, Suite 400",
			"trustee_name": "Demo Corporate Trustees Ltd",
			"auditor_name": "Demo Audit Partners LLP",
			"fees": [
				{
					"fee_type": "Management Fee",
					"calculation_basis": "GAV",
					"annual_percentage": 1.5,
					"accrual_frequency": "Daily",
					"day_count_convention": "ACT/365F",
				},
				{
					"fee_type": "Trustee Fee",
					"calculation_basis": "Prior NAV",
					"annual_percentage": 0.15,
					"accrual_frequency": "Daily",
					"day_count_convention": "ACT/365F",
				},
				{
					"fee_type": "Custody Fee",
					"calculation_basis": "Prior NAV",
					"annual_percentage": 0.10,
					"accrual_frequency": "Daily",
					"day_count_convention": "ACT/365F",
				},
				{
					"fee_type": "Regulatory Fee",
					"calculation_basis": "Prior NAV",
					"annual_percentage": 0.05,
					"accrual_frequency": "Daily",
					"day_count_convention": "ACT/365F",
				},
			],
		},
		{
			"fund_id": "DEMO-BAL",
			"fund_name": "Demo Balanced Fund",
			"fund_type": "Balanced Fund",
			"launch_date": "2024-01-01",
			"currency": currency,
			"status": "Active",
			"accounting_basis": "Mark-to-Market",
			"initial_nav_per_unit": 100.0,
			"current_nav_per_unit": 115.20,
			"current_bid_price": 114.048,
			"current_offer_price": 116.352,
			"bid_offer_spread_pct": 1.0,
			"prior_day_valuation_approved": 1,
			"last_valuation_date": nowdate(),
			"min_subscription_amount": 250.0,
			"min_additional_amount": 100.0,
			"min_redemption_amount": 100.0,
			"min_balance_amount": 100.0,
			"custodian_name": "Demo Global Custody Services",
			"custodian_account": "CUST-DEMO-002",
			"custodian_address": "100 Financial District, Suite 400",
			"trustee_name": "Demo Corporate Trustees Ltd",
			"auditor_name": "Demo Audit Partners LLP",
			"fees": [
				{
					"fee_type": "Management Fee",
					"calculation_basis": "GAV",
					"annual_percentage": 2.0,
					"accrual_frequency": "Daily",
					"day_count_convention": "ACT/365F",
				},
				{
					"fee_type": "Trustee Fee",
					"calculation_basis": "Prior NAV",
					"annual_percentage": 0.20,
					"accrual_frequency": "Daily",
					"day_count_convention": "ACT/365F",
				},
				{
					"fee_type": "Custody Fee",
					"calculation_basis": "Prior NAV",
					"annual_percentage": 0.15,
					"accrual_frequency": "Daily",
					"day_count_convention": "ACT/365F",
				},
				{
					"fee_type": "Regulatory Fee",
					"calculation_basis": "Prior NAV",
					"annual_percentage": 0.05,
					"accrual_frequency": "Daily",
					"day_count_convention": "ACT/365F",
				},
			],
		},
	]

	created: list[str] = []
	for fdata in demo_funds:
		fund_id = fdata["fund_id"]
		target_status = fdata.get("status", "Active")
		if not frappe.db.exists("Asset Fund", fund_id):
			doc = frappe.get_doc({**fdata, "doctype": "Asset Fund", "status": "Suspended"})
			# System setup job: ignore_permissions required
			doc.insert(ignore_permissions=True)
		setup_fund_accounts(fund_id)
		frappe.db.set_value("Asset Fund", fund_id, "status", target_status)
		created.append(fund_id)

	return created


def _ensure_demo_agents() -> list[str]:
	"""Creates two neutral demo agents."""
	demo_agents = [
		{
			"agent_code": "AGT-DEMO-001",
			"agent_name": "Alpha Wealth Advisory Ltd",
			"agent_type": "Corporate / Broker",
			"status": "Active",
			"cma_license_no": "LIC-AGT-2026-001",
			"commission_rate_pct": 1.25,
			"email": "advisory@alphawealth.example.com",
			"phone": "+1-555-010-1001",
			"bank_name": "First Commercial Bank",
			"bank_account_no": "901000112233",
		},
		{
			"agent_code": "AGT-DEMO-002",
			"agent_name": "Jordan Taylor (Independent Advisor)",
			"agent_type": "Individual",
			"status": "Active",
			"cma_license_no": "LIC-AGT-2026-002",
			"commission_rate_pct": 1.0,
			"email": "jtaylor@advisors.example.com",
			"phone": "+1-555-010-1002",
			"bank_name": "Metro Clearing Bank",
			"bank_account_no": "802000445566",
		},
	]

	created: list[str] = []
	for adata in demo_agents:
		code = adata["agent_code"]
		if not frappe.db.exists("Asset Agent", code):
			doc = frappe.get_doc({"doctype": "Asset Agent", **adata})
			# System setup job: ignore_permissions required
			doc.insert(ignore_permissions=True)
		created.append(code)

	return created


def _ensure_demo_securities(currency: str = "USD") -> list[str]:
	"""Creates the five generic demo securities."""
	demo_securities = [
		{
			"security_id": "DEMO-GOV-2030",
			"security_name": "Demo Government Bond 2030",
			"asset_class": "Treasury Bond",
			"issuer": "Sovereign Treasury",
			"issuer_type": "Government",
			"sector": "Sovereign",
			"isin": "US0000DEMO01",
			"currency": currency,
			"status": "Active",
			"issue_date": "2023-06-15",
			"maturity_date": "2030-06-15",
			"coupon_rate": 8.5,
			"coupon_frequency": "Semi-Annual",
			"day_count_convention": "Actual/365",
			"current_market_price": 101.25,
			"yield_to_maturity": 8.20,
		},
		{
			"security_id": "DEMO-TBILL-364D",
			"security_name": "Demo Treasury Bill 364D",
			"asset_class": "Treasury Bill",
			"issuer": "Sovereign Treasury",
			"issuer_type": "Government",
			"sector": "Sovereign",
			"isin": "US0000DEMO02",
			"currency": currency,
			"status": "Active",
			"issue_date": "2026-01-15",
			"maturity_date": "2027-01-14",
			"coupon_rate": 0.0,
			"coupon_frequency": "At Maturity",
			"day_count_convention": "Actual/365",
			"current_market_price": 91.50,
			"yield_to_maturity": 9.30,
		},
		{
			"security_id": "DEMO-FD-180D",
			"security_name": "Demo Bank Fixed Deposit 180D",
			"asset_class": "Fixed Deposit",
			"issuer": "First Commercial Bank",
			"issuer_type": "Commercial Bank",
			"sector": "Financial Services",
			"isin": "US0000DEMO03",
			"currency": currency,
			"status": "Active",
			"issue_date": "2026-06-01",
			"maturity_date": "2026-11-28",
			"coupon_rate": 7.75,
			"coupon_frequency": "At Maturity",
			"day_count_convention": "Actual/365",
			"current_market_price": 100.0,
			"yield_to_maturity": 7.75,
		},
		{
			"security_id": "DEMO-EQ-A",
			"security_name": "Demo Listed Equity A",
			"asset_class": "Quoted Equity",
			"issuer": "Demo Industrial Holdings PLC",
			"issuer_type": "Corporate",
			"sector": "Manufacturing",
			"isin": "US0000DEMO04",
			"currency": currency,
			"status": "Active",
			"issue_date": "2020-01-01",
			"coupon_rate": 0.0,
			"coupon_frequency": "Annual",
			"day_count_convention": "Actual/365",
			"current_market_price": 245.0,
			"yield_to_maturity": 4.5,
		},
		{
			"security_id": "DEMO-CORP-2028",
			"security_name": "Demo Corporate Bond 2028",
			"asset_class": "Corporate Bond",
			"issuer": "Demo Utilities Corp",
			"issuer_type": "Corporate",
			"sector": "Energy",
			"isin": "US0000DEMO05",
			"currency": currency,
			"status": "Active",
			"issue_date": "2023-09-01",
			"maturity_date": "2028-09-01",
			"coupon_rate": 9.25,
			"coupon_frequency": "Semi-Annual",
			"day_count_convention": "Actual/365",
			"current_market_price": 99.80,
			"yield_to_maturity": 9.35,
		},
	]

	created: list[str] = []
	for sdata in demo_securities:
		code = sdata["security_id"]
		if not frappe.db.exists("Asset Investment Security", code):
			doc = frappe.get_doc({"doctype": "Asset Investment Security", **sdata})
			# System setup job: ignore_permissions required
			doc.insert(ignore_permissions=True)
		created.append(code)

	return created


def _ensure_demo_limits() -> list[str]:
	"""Creates sample investment compliance limits for the demo funds."""
	demo_limits = [
		(
			"LIM-DEMO-MMF-GOV",
			{
				"fund": "DEMO-MMF",
				"rule_type": "Asset Class Limit",
				"target_asset_class": "Treasury Bond",
				"min_allocation_pct": 20.0,
				"max_allocation_pct": 85.0,
				"enforce_strict_block": 1,
			},
		),
		(
			"LIM-DEMO-MMF-FD",
			{
				"fund": "DEMO-MMF",
				"rule_type": "Asset Class Limit",
				"target_asset_class": "Fixed Deposit",
				"min_allocation_pct": 15.0,
				"max_allocation_pct": 80.0,
				"enforce_strict_block": 1,
			},
		),
		(
			"LIM-DEMO-BAL-EQ",
			{
				"fund": "DEMO-BAL",
				"rule_type": "Asset Class Limit",
				"target_asset_class": "Quoted Equity",
				"min_allocation_pct": 10.0,
				"max_allocation_pct": 60.0,
				"enforce_strict_block": 1,
			},
		),
	]

	created: list[str] = []
	for code, ldata in demo_limits:
		if not frappe.db.exists("Asset Investment Limit Setup", code):
			doc = frappe.get_doc({"doctype": "Asset Investment Limit Setup", **ldata})
			# System setup job: ignore_permissions required
			doc.insert(ignore_permissions=True, set_name=code)
		created.append(code)

	return created


def run() -> dict[str, Any]:
	"""Idempotent entry point to provision demo fund manager, funds, agents, securities, and limits."""
	currency = frappe.db.get_single_value("System Settings", "currency") or "USD"
	country = frappe.db.get_single_value("System Settings", "country") or "United States"

	fm_company = _ensure_fund_manager_company("Demo Fund Manager", currency=currency, country=country)
	funds = _ensure_demo_funds(currency=currency)
	agents = _ensure_demo_agents()
	securities = _ensure_demo_securities(currency=currency)
	limits = _ensure_demo_limits()

	return {
		"fund_manager_company": fm_company,
		"funds": funds,
		"agents": agents,
		"securities": securities,
		"limits": limits,
	}
