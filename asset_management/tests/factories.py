"""Shared test factories for asset_management (Task R-04).

All tests use these helpers instead of relying on pre-loaded fixture data.
"""

from typing import Any

import frappe
from frappe.utils import flt, nowdate

from asset_management.services.fund_setup import (
	ensure_root_department_exists,
	find_parent_account,
	seed_default_account_templates,
	setup_fund_accounts,
)


def make_checker_user(email: str = "checker.ops@example.com") -> str:
	"""Ensures a distinct checker user exists with operational/admin roles for maker-checker."""
	if not frappe.db.exists("User", email):
		u = frappe.new_doc("User")
		u.email = email
		u.first_name = "Checker"
		u.last_name = "Officer"
		u.enabled = 1
		u.send_welcome_email = 0
		# Test factory setup: ignore_permissions required
		u.insert(ignore_permissions=True)

	user_doc = frappe.get_doc("User", email)
	existing_roles = {r.role for r in user_doc.roles}
	needed_roles = [
		"System Manager",
		"Asset Management Operations",
		"Asset Management Admin",
		"Asset Fund Administrator",
		"Asset Finance Officer",
		"Asset Compliance Officer",
		"Asset Investment Manager",
	]
	added = False
	for role_name in needed_roles:
		if frappe.db.exists("Role", role_name) and role_name not in existing_roles:
			user_doc.append("roles", {"role": role_name})
			added = True
	if added:
		# Test factory setup: ignore_permissions required
		user_doc.save(ignore_permissions=True)

	return email


def make_fund_manager_company(
	company_name: str = "Test Fund Manager",
	currency: str = "USD",
	country: str = "United States",
) -> str:
	"""Ensures a Fund Manager company and its commission accounts exist in Fund Management Settings."""
	ensure_root_department_exists()
	if not frappe.db.exists("Company", company_name):
		comp = frappe.new_doc("Company")
		comp.company_name = company_name
		abbr = "TFM"
		suffix = 1
		while frappe.db.exists("Company", {"abbr": abbr}):
			abbr = f"TFM{suffix}"
			suffix += 1
		comp.abbr = abbr
		comp.default_currency = currency
		comp.country = country
		comp.chart_of_accounts = "Standard"
		comp.default_payroll_payable_account = None
		# Test factory setup: ignore_permissions required
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
		# Test factory setup: ignore_permissions required
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
		# Test factory setup: ignore_permissions required
		doc.insert(ignore_permissions=True)
		pay_acc = doc.name

	seed_default_account_templates(backfill_existing=False)
	settings = frappe.get_single("Fund Management Settings")
	settings.fund_manager_company = company_name
	settings.commission_expense_account = exp_acc
	settings.commission_payable_account = pay_acc
	if not settings.regulatory_fee_label:
		settings.regulatory_fee_label = "Regulatory Fee"
	# Test factory setup: ignore_permissions required
	settings.save(ignore_permissions=True)

	return company_name


def make_approved_valuation(
	fund: str,
	date: str | None = None,
	nav: float = 100.0,
	bid: float | None = None,
	offer: float | None = None,
) -> Any:
	"""Publishes an approved Asset Fund Price for (fund, date) and marks prior-day valuation approved."""
	price_date = date or nowdate()
	nav_val = flt(nav, 6)
	bid_val = flt(bid if bid is not None else nav_val, 6)
	offer_val = flt(offer if offer is not None else nav_val, 6)

	existing_name = frappe.db.get_value("Asset Fund Price", {"fund": fund, "price_date": price_date}, "name")
	prev_flag = getattr(frappe.flags, "in_valuation_submit", False)
	frappe.flags.in_valuation_submit = True
	try:
		if existing_name:
			price_doc = frappe.get_doc("Asset Fund Price", existing_name)
			price_doc.nav_per_unit = nav_val
			price_doc.bid_price = bid_val
			price_doc.offer_price = offer_val
			price_doc.flags.ignore_mandatory = True
			price_doc.flags.ignore_links = True
			# Test factory setup: ignore_permissions required
			price_doc.save(ignore_permissions=True)
		else:
			price_doc = frappe.get_doc(
				{
					"doctype": "Asset Fund Price",
					"fund": fund,
					"price_date": price_date,
					"nav_per_unit": nav_val,
					"bid_price": bid_val,
					"offer_price": offer_val,
				}
			)
			price_doc.flags.ignore_mandatory = True
			price_doc.flags.ignore_links = True
			# Test factory setup: ignore_permissions required
			price_doc.insert(ignore_permissions=True)
	finally:
		frappe.flags.in_valuation_submit = prev_flag

	frappe.db.set_value(
		"Asset Fund",
		fund,
		{
			"current_nav_per_unit": nav_val,
			"current_bid_price": bid_val,
			"current_offer_price": offer_val,
			"prior_day_valuation_approved": 1,
			"last_valuation_date": price_date,
		},
	)
	return price_doc


_FUND_TYPE_MAP = {
	"Money Market": "Money Market Fund",
	"Balanced": "Balanced Fund",
	"Fixed Income / Bond Fund": "Bond Fund",
	"Equity": "Equity Fund",
}


def make_fund(
	fund_id: str = "TEST-MMF",
	fund_name: str | None = None,
	fund_type: str = "Money Market Fund",
	accounts: bool = True,
	nav: float = 100.0,
	bid: float | None = None,
	offer: float | None = None,
	currency: str = "USD",
	price_date: str | None = None,
	**kwargs: Any,
) -> Any:
	"""Creates or updates a neutral Asset Fund, optionally provisioning its Company/COA and price."""
	make_fund_manager_company(currency=currency)
	resolved_name = fund_name or f"Test {fund_id} Fund"
	resolved_type = _FUND_TYPE_MAP.get(fund_type, fund_type)
	nav_val = flt(nav if nav and nav > 0 else 100.0, 6)
	bid_val = flt(bid if bid is not None else nav_val, 6)
	offer_val = flt(offer if offer is not None else nav_val, 6)
	target_status = kwargs.pop("status", "Active")
	prior_approved = kwargs.pop("prior_day_valuation_approved", 1)

	if not frappe.db.exists("Asset Fund", fund_id):
		fee_rows = kwargs.pop(
			"fees",
			kwargs.pop(
				"fee_schedule",
				[
					{
						"fee_type": "Management Fee",
						"calculation_basis": "GAV",
						"annual_percentage": kwargs.get("management_fee_pct", 2.0),
						"accrual_frequency": "Daily",
						"day_count_convention": "ACT/365F",
					},
					{
						"fee_type": "Trustee Fee",
						"calculation_basis": "Prior NAV",
						"annual_percentage": kwargs.get("trustee_fee_pct", 0.15),
						"accrual_frequency": "Daily",
						"day_count_convention": "ACT/365F",
					},
					{
						"fee_type": "Custody Fee",
						"calculation_basis": "Prior NAV",
						"annual_percentage": kwargs.get("custody_fee_pct", 0.10),
						"accrual_frequency": "Daily",
						"day_count_convention": "ACT/365F",
					},
					{
						"fee_type": "Regulatory Fee",
						"calculation_basis": "Prior NAV",
						"annual_percentage": kwargs.get("regulatory_fee_pct", 0.05),
						"accrual_frequency": "Daily",
						"day_count_convention": "ACT/365F",
					},
				],
			),
		)
		data = {
			"doctype": "Asset Fund",
			"fund_id": fund_id,
			"fund_name": resolved_name,
			"fund_type": resolved_type,
			"launch_date": kwargs.pop("launch_date", kwargs.pop("inception_date", "2024-01-01")),
			"currency": currency,
			"status": "Suspended" if accounts else target_status,
			"initial_nav_per_unit": kwargs.pop(
				"initial_nav_per_unit", kwargs.pop("initial_unit_price", 100.0)
			),
			"current_nav_per_unit": nav_val,
			"current_bid_price": bid_val,
			"current_offer_price": offer_val,
			"prior_day_valuation_approved": prior_approved,
			"last_valuation_date": price_date or nowdate(),
			"min_subscription_amount": kwargs.pop("min_subscription_amount", 100.0),
			"min_additional_amount": kwargs.pop("min_additional_amount", 50.0),
			"min_redemption_amount": kwargs.pop("min_redemption_amount", 50.0),
			"min_balance_amount": kwargs.pop("min_balance_amount", 0.0),
			"custodian_name": kwargs.pop("custodian_name", "Global Custody Services"),
			"custodian_account": kwargs.pop("custodian_account", "CUST-001"),
			"custodian_address": kwargs.pop("custodian_address", "100 Financial Plaza"),
			"trustee_name": kwargs.pop("trustee_name", "Corporate Trustees Ltd"),
			"auditor_name": kwargs.pop("auditor_name", "Independent Audit LLP"),
			"fees": fee_rows,
			**kwargs,
		}
		doc = frappe.get_doc(data)
		# Test factory setup: ignore_permissions required
		doc.insert(ignore_permissions=True)
	else:
		doc = frappe.get_doc("Asset Fund", fund_id)
		if kwargs:
			for k, v in kwargs.items():
				setattr(doc, k, v)
			# Test factory setup: ignore_permissions required
			doc.save(ignore_permissions=True)

	if accounts:
		setup_fund_accounts(fund_id)
		frappe.db.set_value("Asset Fund", fund_id, "status", target_status)
		doc.reload()

	if nav and nav > 0:
		make_approved_valuation(
			fund_id,
			date=price_date or nowdate(),
			nav=nav_val,
			bid=doc.current_bid_price or bid_val,
			offer=doc.current_offer_price or offer_val,
		)
		if not prior_approved:
			frappe.db.set_value("Asset Fund", fund_id, "prior_day_valuation_approved", 0)
		doc.reload()

	return doc


def make_investor(
	active: bool = True,
	investor_name: str | None = None,
	investor_type: str = "Individual",
	**kwargs: Any,
) -> Any:
	"""Creates a neutral Asset Investor and its linked Unit Holders Supplier."""
	suffix = frappe.generate_hash(length=6).upper()
	inv_id = kwargs.pop("investor_id", f"INV-{suffix}")
	if frappe.db.exists("Asset Investor", inv_id):
		doc = frappe.get_doc("Asset Investor", inv_id)
		updated = False
		if investor_name and doc.investor_name != investor_name:
			doc.investor_name = investor_name
			updated = True
		for k, v in kwargs.items():
			if getattr(doc, k, None) != v:
				setattr(doc, k, v)
				updated = True
		if updated:
			# Test factory setup: ignore_permissions required
			doc.save(ignore_permissions=True)
		return doc

	name_val = investor_name or f"Test Investor {suffix}"
	status_val = "Active" if active else kwargs.pop("status", "Suspended")

	data = {
		"doctype": "Asset Investor",
		"investor_id": inv_id,
		"investor_name": name_val,
		"investor_type": investor_type,
		"status": status_val,
		"kyc_status": "Verified" if active else "Pending",
		"tax_id": kwargs.pop("tax_id", kwargs.pop("tax_id_tin", f"TIN-{suffix}")),
		"identification_no": kwargs.pop("identification_no", kwargs.pop("national_id_nin", f"ID-{suffix}01")),
		"email": kwargs.pop("email", f"investor.{suffix.lower()}@example.com"),
		"phone": kwargs.pop("phone", "+1-555-019-9000"),
		"country_of_residence": kwargs.pop("country_of_residence", kwargs.pop("country", "United States")),
		"bank_name": kwargs.pop("bank_name", "First Settlement Bank"),
		"bank_branch": kwargs.pop("bank_branch", "Main Branch"),
		"bank_account_no": kwargs.pop("bank_account_no", f"9900{suffix}"),
		"bank_account_name": kwargs.pop("bank_account_name", name_val),
		**kwargs,
	}
	doc = frappe.get_doc(data)
	# Test factory setup: ignore_permissions required
	doc.insert(ignore_permissions=True)
	doc.reload()
	return doc


def make_agent(
	agent_code: str | None = None,
	agent_name: str | None = None,
	commission_rate_pct: float = 1.25,
	**kwargs: Any,
) -> Any:
	"""Creates or fetches an Asset Agent."""
	code = agent_code or f"AGT-{frappe.generate_hash(length=4).upper()}"
	if frappe.db.exists("Asset Agent", code):
		return frappe.get_doc("Asset Agent", code)

	agent_type = kwargs.pop("agent_type", "Corporate / Broker")
	if agent_type == "Corporate":
		agent_type = "Corporate / Broker"

	doc = frappe.get_doc(
		{
			"doctype": "Asset Agent",
			"agent_code": code,
			"agent_name": agent_name or f"Advisor {code}",
			"agent_type": agent_type,
			"status": kwargs.pop("status", "Active"),
			"cma_license_no": kwargs.pop("cma_license_no", f"LIC-{code}"),
			"commission_rate_pct": commission_rate_pct,
			"email": kwargs.pop("email", f"{code.lower()}@advisors.example.com"),
			"phone": kwargs.pop("phone", "+1-555-010-2000"),
			"bank_name": kwargs.pop("bank_name", "First Commercial Bank"),
			"bank_account_no": kwargs.pop("bank_account_no", "901000998877"),
			**kwargs,
		}
	)
	# Test factory setup: ignore_permissions required
	doc.insert(ignore_permissions=True)
	return doc


_ASSET_CLASS_MAP = {
	"Government Securities": "Treasury Bond",
	"Money Market": "Fixed Deposit",
	"Equities": "Quoted Equity",
	"Listed Equity": "Quoted Equity",
	"Corporate Debt": "Corporate Bond",
}

_DAY_COUNT_MAP = {
	"ACT/365": "Actual/365",
	"ACT/364": "Actual/365",
	"ACT/ACT": "Actual/Actual",
}


def make_security(
	security_code: str = "TEST-BOND-2030",
	security_name: str | None = None,
	instrument_type: str = "Treasury Bond",
	asset_class: str = "Treasury Bond",
	coupon_rate_pct: float = 10.0,
	current_market_price: float = 100.0,
	currency: str = "USD",
	**kwargs: Any,
) -> Any:
	"""Creates or fetches an Asset Investment Security."""
	sec_id = kwargs.pop("security_id", security_code)
	if frappe.db.exists("Asset Investment Security", sec_id):
		return frappe.get_doc("Asset Investment Security", sec_id)

	resolved_class = _ASSET_CLASS_MAP.get(asset_class, _ASSET_CLASS_MAP.get(instrument_type, asset_class))
	valid_classes = {
		"Treasury Bond",
		"Corporate Bond",
		"Treasury Bill",
		"Fixed Deposit",
		"Call Deposit",
		"Commercial Paper",
		"Quoted Equity",
	}
	if resolved_class not in valid_classes:
		resolved_class = instrument_type if instrument_type in valid_classes else "Treasury Bond"

	raw_dc = kwargs.pop("day_count_convention", "Actual/365")
	resolved_dc = _DAY_COUNT_MAP.get(raw_dc, raw_dc)
	if resolved_dc not in {"Actual/365", "Actual/Actual", "30/360"}:
		resolved_dc = "Actual/365"

	raw_freq = kwargs.pop("coupon_frequency", "Semi-Annual")
	if raw_freq not in {"Semi-Annual", "Annual", "Quarterly", "At Maturity"}:
		raw_freq = "At Maturity"

	coupon_val = kwargs.pop("coupon_rate", coupon_rate_pct)

	doc = frappe.get_doc(
		{
			"doctype": "Asset Investment Security",
			"security_id": sec_id,
			"security_name": security_name or f"Security {sec_id}",
			"asset_class": resolved_class,
			"issuer": kwargs.pop("issuer", "Sovereign Treasury"),
			"issuer_type": kwargs.pop("issuer_type", "Government"),
			"sector": kwargs.pop("sector", "Sovereign"),
			"isin": kwargs.pop("isin", f"US00{sec_id[:8]}"),
			"currency": currency,
			"status": kwargs.pop("status", "Active"),
			"issue_date": kwargs.pop("issue_date", "2024-01-01"),
			"maturity_date": kwargs.pop("maturity_date", "2030-01-01"),
			"coupon_rate": coupon_val,
			"coupon_frequency": raw_freq,
			"day_count_convention": resolved_dc,
			"current_market_price": current_market_price,
			"yield_to_maturity": kwargs.pop(
				"yield_to_maturity", kwargs.pop("current_yield_to_maturity_pct", coupon_val)
			),
			**kwargs,
		}
	)
	# Test factory setup: ignore_permissions required
	doc.insert(ignore_permissions=True)
	return doc


def make_security_price(
	security: str,
	price_date: str | None = None,
	clean_price: float = 100.0,
	yield_pct: float = 10.0,
	source: str = "Manual",
) -> Any:
	"""Creates or updates an Asset Security Price record for (security, price_date)."""
	pdate = price_date or nowdate()
	existing = frappe.db.get_value(
		"Asset Security Price", {"security": security, "price_date": pdate}, "name"
	)
	if existing:
		doc = frappe.get_doc("Asset Security Price", existing)
		doc.clean_price = flt(clean_price, 6)
		doc.yield_pct = flt(yield_pct, 6)
		doc.source = source
		# Test factory setup: ignore_permissions required
		doc.save(ignore_permissions=True)
		return doc

	doc = frappe.get_doc(
		{
			"doctype": "Asset Security Price",
			"security": security,
			"price_date": pdate,
			"clean_price": flt(clean_price, 6),
			"yield_pct": flt(yield_pct, 6),
			"source": source,
		}
	)
	# Test factory setup: ignore_permissions required
	doc.insert(ignore_permissions=True)
	return doc


def make_subscription(
	investor: str,
	fund: str,
	amount: float = 1_000_000.0,
	subscription_date: str | None = None,
	entry_fee_pct: float = 0.0,
	agent: str | None = None,
	submit: bool = True,
	checker_user: str = "checker.ops@example.com",
	**kwargs: Any,
) -> Any:
	"""Creates (and optionally submits as checker) an Asset Subscription."""
	sub_date = subscription_date or nowdate()
	checker = make_checker_user(checker_user)
	doc = frappe.get_doc(
		{
			"doctype": "Asset Subscription",
			"investor": investor,
			"fund": fund,
			"subscription_date": sub_date,
			"value_date": kwargs.pop("value_date", sub_date),
			"gross_amount": amount,
			"entry_fee_pct": entry_fee_pct,
			"agent": agent,
			"maker": "Administrator",
			"checker": checker,
			"payment_mode": kwargs.pop("payment_mode", "Bank Transfer / BOL"),
			"payment_reference": kwargs.pop(
				"payment_reference", f"REF-{frappe.generate_hash(length=6).upper()}"
			),
			**kwargs,
		}
	)
	# Test factory setup: ignore_permissions required
	doc.insert(ignore_permissions=True)

	if submit:
		doc.approved_by_operations = 1
		doc.checker_approved = 1
		doc.workflow_state = "Approved"
		doc.submit()

	return doc


def make_redemption(
	investor: str,
	fund: str,
	units: float | None = None,
	amount: float | None = None,
	redemption_date: str | None = None,
	exit_fee_pct: float = 0.0,
	wht_rate: float | None = None,
	wht_basis: str | None = None,
	submit: bool = True,
	checker_user: str = "checker.ops@example.com",
	**kwargs: Any,
) -> Any:
	"""Creates (and optionally submits as checker) an Asset Redemption."""
	red_date = redemption_date or nowdate()
	checker = make_checker_user(checker_user)
	redemption_by = "Amount" if (amount is not None and units is None) else "Units"
	data: dict[str, Any] = {
		"doctype": "Asset Redemption",
		"investor": investor,
		"fund": fund,
		"redemption_date": red_date,
		"value_date": kwargs.pop("value_date", red_date),
		"redemption_by": redemption_by,
		"exit_fee_pct": exit_fee_pct,
		"prior_day_valuation_approved": 1,
		"maker": "Administrator",
		"checker": checker,
		**kwargs,
	}
	if redemption_by == "Units":
		data["requested_units"] = units
	else:
		data["requested_amount"] = amount

	if wht_rate is not None:
		data["wht_rate_pct"] = wht_rate
	if wht_basis is not None:
		data["wht_basis"] = wht_basis

	doc = frappe.get_doc(data)
	# Test factory setup: ignore_permissions required
	doc.insert(ignore_permissions=True)

	if submit:
		doc.checker_approved = 1
		doc.workflow_state = "Approved"
		doc.submit()

	return doc
