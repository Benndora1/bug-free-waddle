"""One-click accounting and company provisioning service for a fund (services/fund_setup.py).

Per ADR-0001, ADR-0006, and Task R-07:
- Each fund is an ERPNext Company with its own isolated Chart of Accounts.
- All fund-level account fields on Asset Fund are populated from Fund Account Template.
- Supplier Group 'Unit Holders' party account is linked to Client Cash Payable for the fund company.
- Fully idempotent: multiple executions produce 0 duplicate records.
"""

from typing import Any

import frappe
from frappe import _

DEFAULT_ACCOUNT_TEMPLATES = [
	("client_cash_payable_account", "Client Cash Payable", "Liability", "Payable", "Current Liabilities", 0),
	("unallocated_receipts_account", "Unallocated Receipts", "Liability", "", "Current Liabilities", 0),
	("unitholders_capital_account", "Unitholders Capital", "Equity", "Equity", "Equity", 0),
	("entry_fee_payable_account", "Entry Fee Payable", "Liability", "", "Current Liabilities", 0),
	("exit_fee_payable_account", "Exit Fee Payable", "Liability", "", "Current Liabilities", 0),
	("wht_payable_account", "WHT Payable", "Liability", "", "Current Liabilities", 0),
	("fees_payable_account", "Fees Payable - Fund Manager", "Liability", "", "Current Liabilities", 0),
	("due_to_other_funds_account", "Due to Other Funds", "Liability", "", "Current Liabilities", 0),
	("due_from_other_funds_account", "Due from Other Funds", "Asset", "Receivable", "Current Assets", 0),
	("interest_receivable_account", "Interest Receivable", "Asset", "", "Current Assets", 0),
	("investments_at_cost_account", "Investments at Cost", "Asset", "", "Current Assets", 1),
	("investment_revaluation_account", "Investment Revaluation", "Asset", "", "Current Assets", 0),
	("interest_income_account", "Interest Income", "Income", "", "Income", 0),
	("unrealised_gain_loss_account", "Unrealised Gain Loss", "Income", "", "Income", 0),
	("realised_gain_loss_account", "Realised Gain Loss", "Income", "", "Income", 0),
	("fund_expenses_account", "Fund Expenses", "Expense", "", "Expenses", 1),
	("rounding_account", "Rounding Adjustment", "Expense", "Round Off", "Expenses", 0),
]


def seed_default_account_templates(backfill_existing: bool = True) -> None:
	"""Ensures default Fund Account Template rows exist in Fund Management Settings."""
	if not frappe.db.exists("DocType", "Fund Management Settings"):
		return

	settings = frappe.get_single("Fund Management Settings")
	existing_rows = {r.key: r for r in getattr(settings, "account_templates", [])}

	updated = False
	for key, name, root_type, acc_type, parent, is_group in DEFAULT_ACCOUNT_TEMPLATES:
		if key not in existing_rows:
			settings.append(
				"account_templates",
				{
					"key": key,
					"account_name": name,
					"root_type": root_type,
					"account_type": acc_type,
					"parent_account_name": parent,
					"is_group": is_group,
				},
			)
			updated = True
		else:
			row = existing_rows[key]
			if row.account_type in ("Expense", "Income"):
				row.account_type = acc_type
				updated = True

	if updated:
		settings.save(ignore_permissions=True)

	# Backfill existing active funds that are missing account fields
	if backfill_existing and frappe.db.exists("DocType", "Asset Fund"):
		fallback_comp = (
			getattr(settings, "default_fund_company", None)
			or getattr(settings, "fund_manager_company", None)
			or frappe.db.get_value("Company", {}, "name")
		)
		active_funds = frappe.get_all("Asset Fund", filters={"status": "Active"}, pluck="name")
		for fname in active_funds:
			fdoc = frappe.get_doc("Asset Fund", fname)
			missing = any(not getattr(fdoc, k[0], None) for k in DEFAULT_ACCOUNT_TEMPLATES)
			target_comp = fdoc.company or fallback_comp
			if missing and target_comp and frappe.db.exists("Company", target_comp):
				if not fdoc.company:
					fdoc.db_set("company", target_comp)
					fdoc.company = target_comp
				provision_accounts_in_company(fdoc, target_comp)


def get_account_templates() -> list[dict[str, Any]]:
	"""Returns the list of active account templates from settings or fallback defaults."""
	if frappe.db.exists("DocType", "Fund Management Settings"):
		settings = frappe.get_single("Fund Management Settings")
		if getattr(settings, "account_templates", None):
			return [
				{
					"key": r.key,
					"account_name": r.account_name,
					"root_type": r.root_type,
					"account_type": r.account_type,
					"parent_account_name": r.parent_account_name,
					"is_group": r.is_group,
				}
				for r in settings.account_templates
			]

	return [
		{
			"key": key,
			"account_name": name,
			"root_type": root_type,
			"account_type": acc_type,
			"parent_account_name": parent,
			"is_group": is_group,
		}
		for key, name, root_type, acc_type, parent, is_group in DEFAULT_ACCOUNT_TEMPLATES
	]


def ensure_root_department_exists() -> None:
	"""Ensures a root Department named 'All Departments' exists without company restriction."""
	if not frappe.db.exists("DocType", "Department"):
		return

	if frappe.db.exists("Department", "All Departments"):
		return

	existing_root = frappe.db.get_value(
		"Department", {"is_group": 1, "parent_department": ["in", [None, ""]]}, "name"
	)
	if existing_root:
		frappe.db.sql(
			"UPDATE `tabDepartment` SET `name`='All Departments', `company`=NULL WHERE `name`=%s",
			(existing_root,),
		)
		return

	dept = frappe.new_doc("Department")
	dept.department_name = "All Departments"
	dept.is_group = 1
	dept.company = None
	dept.parent_department = None
	dept.flags.ignore_mandatory = True
	dept.insert(ignore_permissions=True)


def find_parent_account(company: str, parent_account_name: str | None, root_type: str) -> str | None:
	"""Finds a suitable parent group account in the company's chart of accounts."""
	abbr = frappe.db.get_value("Company", company, "abbr")
	if parent_account_name:
		# 1. Direct match by account_name or full name
		direct = frappe.db.get_value(
			"Account",
			{"company": company, "is_group": 1, "account_name": parent_account_name},
			"name",
		)
		if direct:
			return direct

		if abbr:
			with_abbr = frappe.db.get_value(
				"Account",
				{"company": company, "is_group": 1, "name": f"{parent_account_name} - {abbr}"},
				"name",
			)
			if with_abbr:
				return with_abbr

	# 2. Fall back to root group account for that root_type
	root_acc = frappe.db.get_value(
		"Account",
		{"company": company, "is_group": 1, "root_type": root_type, "parent_account": ["in", [None, ""]]},
		"name",
	)
	if root_acc:
		return root_acc

	# 3. Any group account of that root type
	any_group = frappe.db.get_value(
		"Account",
		{"company": company, "is_group": 1, "root_type": root_type},
		"name",
	)
	return any_group


def provision_accounts_in_company(fund_doc: Any, company_name: str) -> None:
	"""Creates template accounts in company_name, assigns them to fund_doc, and maps Unit Holders."""
	templates = get_account_templates()
	abbr = frappe.db.get_value("Company", company_name, "abbr")
	comp_currency = (
		frappe.db.get_value("Company", company_name, "default_currency") or fund_doc.currency or "USD"
	)

	for tmpl in templates:
		key = tmpl["key"]
		acc_name = tmpl["account_name"]
		root_type = tmpl["root_type"]
		acc_type = tmpl.get("account_type") or None
		if acc_type in ("Expense", "Income", "None", ""):
			acc_type = None
		parent_hint = tmpl.get("parent_account_name")
		is_group = 1 if tmpl.get("is_group") else 0

		existing = frappe.db.get_value(
			"Account",
			{"company": company_name, "account_name": acc_name},
			"name",
		)
		if not existing and abbr:
			existing = frappe.db.get_value(
				"Account",
				{"company": company_name, "name": f"{acc_name} - {abbr}"},
				"name",
			)

		if not existing:
			parent_account = find_parent_account(company_name, parent_hint, root_type)
			if not parent_account:
				frappe.throw(
					_("Could not locate parent account for {0} (root_type: {1}) in company {2}.").format(
						acc_name, root_type, company_name
					)
				)

			new_acc = frappe.new_doc("Account")
			new_acc.account_name = acc_name
			new_acc.company = company_name
			new_acc.parent_account = parent_account
			new_acc.root_type = root_type
			if acc_type:
				new_acc.account_type = acc_type
			new_acc.is_group = is_group
			new_acc.account_currency = comp_currency
			new_acc.insert(ignore_permissions=True)
			existing = new_acc.name

		setattr(fund_doc, key, existing)
		fund_doc.db_set(key, existing)

	if not frappe.db.exists("Supplier Group", "Unit Holders"):
		sg = frappe.new_doc("Supplier Group")
		sg.supplier_group_name = "Unit Holders"
		sg.insert(ignore_permissions=True)

	sg = frappe.get_doc("Supplier Group", "Unit Holders")
	has_party_acc = any(r.company == company_name for r in sg.accounts)
	if not has_party_acc:
		cash_acc = fund_doc.client_cash_payable_account
		if cash_acc:
			sg.append(
				"accounts",
				{
					"company": company_name,
					"account": cash_acc,
				},
			)
			sg.save(ignore_permissions=True)


def setup_fund_accounts(fund: str) -> None:
	"""Provisions the ERPNext Company, Chart of Accounts, and Supplier Group party mapping for a fund.

	Idempotent: safe to run multiple times.
	"""
	if not fund or not frappe.db.exists("Asset Fund", fund):
		frappe.throw(_("Asset Fund {0} not found.").format(fund))

	seed_default_account_templates(backfill_existing=False)
	fund_doc = frappe.get_doc("Asset Fund", fund)

	# 1. Resolve or Create Company
	settings = (
		frappe.get_single("Fund Management Settings")
		if frappe.db.exists("DocType", "Fund Management Settings")
		else None
	)
	fm_comp = getattr(settings, "fund_manager_company", None)
	default_comp = (
		frappe.db.get_single_value("Global Defaults", "default_company")
		if frappe.db.exists("DocType", "Global Defaults")
		else None
	)
	user_default_comp = frappe.defaults.get_user_default("Company")

	company_name = fund_doc.company
	shared_with_other_fund = bool(
		company_name
		and frappe.db.exists("Asset Fund", {"company": company_name, "name": ["!=", fund_doc.name]})
	)
	is_auto_default = bool(
		company_name
		and company_name != fund_doc.fund_name
		and company_name in {c for c in (fm_comp, default_comp, user_default_comp) if c}
	)
	if (
		not company_name
		or not frappe.db.exists("Company", company_name)
		or is_auto_default
		or shared_with_other_fund
	):
		# Look for existing company with this fund_name
		existing_company = frappe.db.get_value("Company", {"company_name": fund_doc.fund_name}, "name")
		if existing_company:
			company_name = existing_company
		else:
			ensure_root_department_exists()
			country = None
			if fm_comp and frappe.db.exists("Company", fm_comp):
				country = frappe.db.get_value("Company", fm_comp, "country")
			if not country:
				country = frappe.db.get_value("Company", {}, "country") or "United States"

			comp = frappe.new_doc("Company")
			comp.company_name = fund_doc.fund_name
			raw_abbr = (
				(fund_doc.fund_id or fund_doc.fund_name[:6])
				.replace("-", "")
				.replace("_", "")
				.replace(" ", "")
				.upper()
			)
			base_abbr = raw_abbr[:5] if len(raw_abbr) <= 5 else (raw_abbr[:3] + raw_abbr[-2:])
			abbr = base_abbr or "FUND"
			suffix = 1
			while frappe.db.exists("Company", {"abbr": abbr}):
				abbr = f"{base_abbr[:4]}{suffix}"
				suffix += 1
			comp.abbr = abbr
			comp.default_currency = fund_doc.currency or "USD"
			comp.country = country
			comp.chart_of_accounts = "Standard"
			comp.default_payroll_payable_account = None
			comp.insert(ignore_permissions=True)
			company_name = comp.name

		fund_doc.db_set("company", company_name)
		fund_doc.company = company_name

	# 2. Provision Accounts and Supplier Group Mapping
	provision_accounts_in_company(fund_doc, company_name)


@frappe.whitelist()
def setup_fund_accounts_api(fund: str) -> dict[str, Any]:
	"""Whitelisted API endpoint for Desk action button 'Set up Accounts' on Asset Fund."""
	roles = frappe.get_roles()
	allowed = {"Asset Management Admin", "Asset Finance Officer", "System Manager", "Administrator"}
	if not any(r in allowed for r in roles):
		frappe.throw(_("Not permitted to set up fund accounts."), frappe.PermissionError)

	setup_fund_accounts(fund)
	return {"status": "success", "message": _("Fund accounts configured successfully.")}
