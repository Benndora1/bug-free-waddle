from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

from asset_management.accounting.posting import post_gl, reverse_gl
from asset_management.services.accrual import FeeRule, calculate_fee_accrual
from asset_management.services.daycount import previous_business_day
from asset_management.services.pricing import get_security_price_for_valuation
from asset_management.services.reconciliation import (
	get_company_gl_assets_and_liabilities,
	reconcile_fund,
)
from asset_management.services.units import get_fund_units_in_issue

MARKET_PRICED_ASSET_CLASSES = {
	"Treasury Bond",
	"Corporate Bond",
	"Treasury Bill",
	"Commercial Paper",
	"Quoted Equity",
}


class AssetFundValuation(Document):
	def validate(self) -> None:
		if not self.valuation_date:
			self.valuation_date = nowdate()

		# 1. Resolve Fund Details (no 100.0 fallback)
		fund = frappe.get_doc("Asset Fund", self.fund)
		self.fund_name = fund.fund_name
		self.currency = fund.currency
		self.bid_offer_spread_pct = flt(fund.bid_offer_spread_pct, 6)

		prev_val = self._get_previous_approved_valuation()
		if prev_val:
			self.previous_valuation = prev_val.name
			self.previous_valuation_date = prev_val.valuation_date
			self.previous_nav_per_unit = flt(prev_val.nav_per_unit, 6)
			start_dt = getdate(prev_val.valuation_date)
			end_dt = getdate(self.valuation_date)
			self.accrual_days = max((end_dt - start_dt).days, 1)
		else:
			self.previous_valuation = None
			self.previous_valuation_date = None
			self.previous_nav_per_unit = flt(fund.initial_nav_per_unit or fund.current_nav_per_unit, 6)
			self.accrual_days = 1

		# 2. Units in issue from immutable Unit Ledger (R-11 item 4)
		ledger_units = get_fund_units_in_issue(self.fund, str(self.valuation_date))
		if ledger_units > Decimal("0.000000"):
			self.total_units_in_issue = float(ledger_units)
		else:
			has_any_ule = frappe.db.exists("Asset Unit Ledger Entry", {"fund": self.fund, "is_cancelled": 0})
			if not has_any_ule and (
				flt(self.total_units_in_issue, 6) > 0 or flt(fund.total_units_in_issue, 6) > 0
			):
				self.total_units_in_issue = flt(self.total_units_in_issue or fund.total_units_in_issue, 6)
			else:
				self.total_units_in_issue = 0.0

		# 3. Auto-load active holdings if lines empty, then value holdings from Asset Security Price
		if not self.lines:
			self.load_active_holdings()
		self.value_holding_lines()

		# 4. Compute Mark-to-Market change vs previous valuation
		self.calculate_mtm_change(prev_val)

		# 5. Aggregate Gross Asset Value (GAV)
		self.aggregate_gav(fund)

		# 6. Accrue Expenses based on Fund Fee Schedule & Day-Count Fraction
		self.calculate_daily_accrued_expenses(fund, prev_val)

		# 7. Calculate NAV & Pricing Output (6 dp)
		self.calculate_nav_and_prices(fund)

	def _get_previous_approved_valuation(self) -> Any | None:
		val_dt = getdate(self.valuation_date)
		rows = frappe.get_all(
			"Asset Fund Valuation",
			filters={
				"fund": self.fund,
				"valuation_date": ["<", val_dt],
				"status": "Approved",
				"docstatus": 1,
				"name": ["!=", self.name or ""],
			},
			fields=[
				"name",
				"valuation_date",
				"total_gav",
				"total_nav",
				"nav_per_unit",
			],
			order_by="valuation_date desc",
			limit=1,
		)
		return rows[0] if rows else None

	def load_active_holdings(self) -> None:
		"""Loads all active securities holdings for this fund (no 100.0 fallback)."""
		holdings = frappe.get_all(
			"Asset Portfolio Holding",
			filters={"fund": self.fund, "holding_status": "Active"},
			fields=[
				"security",
				"asset_class",
				"face_value",
				"carrying_cost",
				"accrued_interest",
				"dirty_market_value",
			],
		)
		self.lines = []
		for h in holdings:
			sec_name = (
				frappe.db.get_value("Asset Investment Security", h.security, "security_name")
				if h.security
				else ""
			) or h.security
			self.append(
				"lines",
				{
					"asset_class": h.asset_class,
					"security": h.security,
					"security_name": sec_name,
					"face_value": flt(h.face_value, 2),
					"carrying_cost": flt(h.carrying_cost, 2),
					"price": 0.0,
					"accrued_interest": flt(h.accrued_interest, 2),
					"dirty_market_value": flt(h.dirty_market_value, 2),
				},
			)

	def value_holding_lines(self) -> None:
		"""Values holding lines using Asset Security Price for valuation_date (or within allowed stale window)."""
		for line in self.lines:
			face_val = Decimal(str(flt(line.face_value, 2))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
			carrying = Decimal(str(flt(getattr(line, "carrying_cost", 0.0), 2))).quantize(
				Decimal("0.01"), rounding=ROUND_HALF_UP
			)
			if carrying == Decimal("0.00") and line.security:
				db_carrying = frappe.db.get_value(
					"Asset Portfolio Holding",
					{"fund": self.fund, "security": line.security, "holding_status": "Active"},
					"carrying_cost",
				)
				if db_carrying:
					carrying = Decimal(str(flt(db_carrying, 2))).quantize(
						Decimal("0.01"), rounding=ROUND_HALF_UP
					)
					line.carrying_cost = float(carrying)

			accrued = Decimal(str(flt(line.accrued_interest, 2))).quantize(
				Decimal("0.01"), rounding=ROUND_HALF_UP
			)

			if line.security and line.asset_class in MARKET_PRICED_ASSET_CLASSES:
				clean_price, price_date_used, is_stale = get_security_price_for_valuation(
					line.security, str(self.valuation_date)
				)
				if clean_price is not None and clean_price > Decimal("0.000000"):
					line.price = float(clean_price)
					line.price_date_used = price_date_used
					line.is_stale_price = 1 if is_stale else 0

					if line.asset_class == "Quoted Equity":
						clean_mv = (face_val * clean_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
					else:
						clean_mv = (face_val * clean_price / Decimal("100")).quantize(
							Decimal("0.01"), rounding=ROUND_HALF_UP
						)

					dirty_mv = (clean_mv + accrued).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
					line.market_value_clean = float(clean_mv)
					line.dirty_market_value = float(dirty_mv)
					base_cost = carrying if carrying > Decimal("0.00") else face_val
					line.unrealised_gain_loss = float(
						(clean_mv - base_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
					)
				else:
					line.price = 0.0
					line.price_date_used = None
					line.is_stale_price = 0
					line.market_value_clean = 0.0
					line.unrealised_gain_loss = 0.0
			else:
				# Fixed Deposit / Call Deposit / Cash line
				clean_mv = carrying if carrying > Decimal("0.00") else face_val
				dirty_mv = (clean_mv + accrued).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
				line.market_value_clean = float(clean_mv)
				if not flt(line.dirty_market_value, 2):
					line.dirty_market_value = float(dirty_mv)
				line.unrealised_gain_loss = 0.0

	def calculate_mtm_change(self, prev_val: Any | None) -> None:
		"""Computes mark-to-market change vs the previous approved valuation."""
		current_unrealised = sum(
			(Decimal(str(flt(getattr(l, "unrealised_gain_loss", 0.0), 2))) for l in self.lines),
			Decimal("0.00"),
		).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

		prev_unrealised = Decimal("0.00")
		if prev_val and prev_val.get("name"):
			prev_doc = frappe.get_doc("Asset Fund Valuation", prev_val.name)
			prev_unrealised = sum(
				(Decimal(str(flt(getattr(l, "unrealised_gain_loss", 0.0), 2))) for l in prev_doc.lines),
				Decimal("0.00"),
			).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

		self.mtm_revaluation_change = float(
			(current_unrealised - prev_unrealised).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
		)

	def aggregate_gav(self, fund: Any) -> None:
		"""Sums holding market values, cash accounts, and interest accruals to establish GAV."""
		bonds = Decimal("0.00")
		tbills = Decimal("0.00")
		deposits = Decimal("0.00")
		equities = Decimal("0.00")

		for l in self.lines:
			mv = Decimal(str(flt(l.dirty_market_value, 2))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
			if l.asset_class in ("Treasury Bond", "Corporate Bond"):
				bonds += mv
			elif l.asset_class in ("Treasury Bill", "Commercial Paper"):
				tbills += mv
			elif l.asset_class in ("Fixed Deposit", "Call Deposit"):
				deposits += mv
			elif l.asset_class == "Quoted Equity":
				equities += mv

		self.bonds_market_value = float(bonds)
		self.tbills_market_value = float(tbills)
		self.deposits_market_value = float(deposits)
		self.equities_market_value = float(equities)

		holdings_subtotal = bonds + tbills + deposits + equities
		accrued_rec = Decimal(str(flt(self.accrued_income_receivable, 2))).quantize(
			Decimal("0.01"), rounding=ROUND_HALF_UP
		)
		daily_int = Decimal(str(flt(getattr(self, "daily_interest_accrual", 0.0), 2))).quantize(
			Decimal("0.01"), rounding=ROUND_HALF_UP
		)

		# If cash_bank_balance is not explicitly provided and the fund has GL net assets from unit dealings,
		# derive cash_bank_balance from the company's pre-valuation GL net assets so GAV tracks GL books.
		cash_bal = Decimal(str(flt(self.cash_bank_balance, 2))).quantize(
			Decimal("0.01"), rounding=ROUND_HALF_UP
		)
		if cash_bal == Decimal("0.00") and fund.company:
			has_ule = frappe.db.exists("Asset Unit Ledger Entry", {"fund": self.fund, "is_cancelled": 0})
			if has_ule:
				exclude = ("Asset Fund Valuation", self.name) if self.name else None
				gl_assets, gl_liab = get_company_gl_assets_and_liabilities(
					fund.company, str(self.valuation_date), exclude_voucher=exclude
				)
				gl_net_before = gl_assets - gl_liab
				if gl_net_before > Decimal("0.00"):
					mtm_chg = Decimal(str(flt(self.mtm_revaluation_change, 2)))
					derived_cash = gl_net_before + mtm_chg - holdings_subtotal - accrued_rec
					if derived_cash >= Decimal("0.00"):
						cash_bal = derived_cash.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

		self.cash_bank_balance = float(cash_bal)
		self.accrued_income_receivable = float(accrued_rec)
		self.daily_interest_accrual = float(daily_int)

		total_gav = (holdings_subtotal + cash_bal + accrued_rec + daily_int).quantize(
			Decimal("0.01"), rounding=ROUND_HALF_UP
		)
		self.total_gav = float(total_gav)

		if total_gav > Decimal("0.00"):
			for l in self.lines:
				mv = Decimal(str(flt(l.dirty_market_value, 2)))
				l.weight_pct = float(
					((mv / total_gav) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
				)

	def calculate_daily_accrued_expenses(self, fund: Any, prev_val: Any | None) -> None:
		"""Computes fee accruals using services/accrual.py and services/daycount.py."""
		end_dt = getdate(self.valuation_date)
		if prev_val and prev_val.get("valuation_date"):
			start_dt = getdate(prev_val.valuation_date)
			prior_nav = Decimal(str(flt(prev_val.total_nav, 2)))
		else:
			start_dt = end_dt - timedelta(days=1)
			prior_nav = Decimal(str(flt(fund.total_nav or self.total_gav, 2)))

		gav_dec = Decimal(str(flt(self.total_gav, 2)))

		mgmt_accrual = Decimal("0.00")
		custody_accrual = Decimal("0.00")
		trustee_accrual = Decimal("0.00")
		cma_accrual = Decimal("0.00")
		audit_accrual = Decimal("0.00")

		if fund.fees:
			for f in fund.fees:
				basis_str = (getattr(f, "calculation_basis", None) or "GAV").strip().upper()
				if basis_str in ("PRIOR NAV", "PRIOR_NAV"):
					basis_amt = prior_nav if prior_nav > Decimal("0.00") else gav_dec
				else:
					basis_amt = gav_dec

				dc = getattr(f, "day_count_convention", None) or "ACT/365F"
				rate = Decimal(str(flt(f.annual_percentage, 6)))
				amt = calculate_fee_accrual(
					basis_amount=basis_amt,
					annual_rate_pct=rate,
					start_date=start_dt,
					end_date=end_dt,
					day_count=dc,
				)

				if f.fee_type == "Management Fee":
					mgmt_accrual += amt
				elif f.fee_type == "Custody Fee":
					custody_accrual += amt
				elif f.fee_type == "Trustee Fee":
					trustee_accrual += amt
				elif f.fee_type == "Regulatory Fee" or (
					f.fee_type and f.fee_type.startswith("Regulatory Fee")
				):
					cma_accrual += amt
				elif f.fee_type == "Audit Fee":
					audit_accrual += amt

		self.management_fee_accrual = float(mgmt_accrual)
		self.custody_fee_accrual = float(custody_accrual)
		self.trustee_fee_accrual = float(trustee_accrual)
		self.cma_regulatory_fee_accrual = float(cma_accrual)
		self.audit_fee_accrual = float(audit_accrual)
		other_liab = Decimal(str(flt(self.other_liabilities, 2))).quantize(
			Decimal("0.01"), rounding=ROUND_HALF_UP
		)
		self.other_liabilities = float(other_liab)

		total_exp = (
			mgmt_accrual + custody_accrual + trustee_accrual + cma_accrual + audit_accrual + other_liab
		).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
		self.total_accrued_expenses = float(total_exp)

	def calculate_nav_and_prices(self, fund: Any) -> None:
		"""Calculates Net Asset Value, NAV per unit (6 dp), and Bid/Offer spread prices (6 dp)."""
		gav = Decimal(str(flt(self.total_gav, 2)))
		exp = Decimal(str(flt(self.total_accrued_expenses, 2)))
		total_nav = (gav - exp).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
		self.total_nav = float(total_nav)

		units = Decimal(str(flt(self.total_units_in_issue, 6)))
		if units > Decimal("0.000000"):
			nav_pu = (total_nav / units).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
		else:
			init_nav = Decimal(str(flt(self.previous_nav_per_unit or fund.initial_nav_per_unit, 6)))
			nav_pu = init_nav.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

		self.nav_per_unit = float(nav_pu)

		spread = Decimal(str(flt(self.bid_offer_spread_pct, 6))) / Decimal("100")
		offer = (nav_pu * (Decimal("1") + spread)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
		bid = (nav_pu * (Decimal("1") - spread)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
		self.offer_price = float(offer)
		self.bid_price = float(bid)

		prev_nav_pu = Decimal(str(flt(self.previous_nav_per_unit, 6)))
		if prev_nav_pu > Decimal("0.000000"):
			chg = (((nav_pu - prev_nav_pu) / prev_nav_pu) * Decimal("100")).quantize(
				Decimal("0.0001"), rounding=ROUND_HALF_UP
			)
			self.daily_change_pct = float(chg)
		else:
			self.daily_change_pct = 0.0

	def before_submit(self) -> None:
		"""Validates Maker-Checker, security prices, D-1 sequential approval, and D-1 NAV reconciliation."""
		if self.prepared_by and self.approved_by and self.prepared_by == self.approved_by:
			frappe.throw(
				_(
					"Maker (prepared_by) and Checker (approved_by) cannot be the same user for Fund Valuation {0}."
				).format(self.name),
				title=_("Maker-Checker Violation"),
			)

		# 1. Re-verify holding security prices on valuation_date (no 100.0 fallback)
		self.value_holding_lines()
		missing_securities: list[str] = []
		for l in self.lines:
			if l.security and l.asset_class in MARKET_PRICED_ASSET_CLASSES:
				if not l.price or flt(l.price, 6) <= 0:
					missing_securities.append(l.security)

		if missing_securities:
			frappe.throw(
				_("Cannot submit valuation for {0} on {1}. Missing Asset Security Price for: {2}.").format(
					self.fund, self.valuation_date, ", ".join(sorted(set(missing_securities)))
				),
				title=_("Missing Security Price"),
			)

		# 2. Sequential Valuation Guard: Date D requires D-1 (previous business day) Approved, except the first
		val_dt = getdate(self.valuation_date)
		duplicate = frappe.db.get_value(
			"Asset Fund Valuation",
			{
				"fund": self.fund,
				"valuation_date": val_dt,
				"status": "Approved",
				"docstatus": 1,
				"name": ["!=", self.name],
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("An Approved valuation ({0}) already exists for fund {1} on {2}.").format(
					duplicate, self.fund, self.valuation_date
				),
				title=_("Duplicate Valuation"),
			)

		any_prior = frappe.get_all(
			"Asset Fund Valuation",
			filters={
				"fund": self.fund,
				"status": "Approved",
				"docstatus": 1,
				"name": ["!=", self.name],
			},
			fields=["name", "valuation_date"],
			order_by="valuation_date desc",
		)
		if any_prior:
			expected_prev_bday = previous_business_day(val_dt)
			has_d_minus_1 = any(getdate(r.valuation_date) == expected_prev_bday for r in any_prior)
			if not has_d_minus_1:
				frappe.throw(
					_(
						"Cannot submit valuation for {0} on {1}: previous business day ({2}) does not have an Approved valuation."
					).format(self.fund, val_dt, expected_prev_bday),
					title=_("Previous Day Valuation Required"),
				)

			# 3. Task R-12 Guard: Reconcile previous valuation date before submitting date D
			prev_val_date = str(expected_prev_bday)
			has_ule = frappe.db.exists(
				"Asset Unit Ledger Entry",
				{"fund": self.fund, "posting_date": ["<=", expected_prev_bday], "is_cancelled": 0},
			)
			if has_ule:
				recon = reconcile_fund(self.fund, prev_val_date)
				if not recon["within_tolerance"]:
					frappe.throw(
						_(
							"Cannot submit valuation for {0} on {1}: prior valuation date {2} failed NAV vs GL reconciliation. "
							"Register Value: {3:,.2f}, GL Net Assets: {4:,.2f}, Difference: {5:,.2f} (Tolerance: {6:,.2f})."
						).format(
							self.fund,
							val_dt,
							prev_val_date,
							float(recon["register_value"]),
							float(recon["gl_net_assets"]),
							float(recon["difference"]),
							float(recon["tolerance"]),
						),
						title=_("Prior Day Reconciliation Failed"),
					)

		if not self.approval_date:
			self.approval_date = nowdate()

	def on_submit(self) -> None:
		"""Creates Asset Fund Price, posts GL entries, updates Fund display cache, and revalues portfolios."""
		fund = frappe.get_doc("Asset Fund", self.fund)

		# 1. Create immutable Asset Fund Price row (R-11 item 1)
		self._create_fund_price_record()

		# 2. Post GL entries in fund's company via accounting/posting.py (R-11 item 6)
		gl_rows = self.get_gl_entries(fund)
		if gl_rows:
			post_gl(self, gl_rows)

		# 3. Update Asset Fund display cache
		fund.current_nav_per_unit = flt(self.nav_per_unit, 6)
		fund.current_offer_price = flt(self.offer_price, 6)
		fund.current_bid_price = flt(self.bid_price, 6)
		fund.total_gav = flt(self.total_gav, 2)
		fund.total_nav = flt(self.total_nav, 2)
		fund.total_units_in_issue = flt(self.total_units_in_issue, 6)
		fund.last_valuation_date = self.valuation_date
		fund.prior_day_valuation_approved = 1
		fund.save(ignore_permissions=True)

		# 4. Mark-to-market revaluation of client portfolios
		portfolios = frappe.get_all("Asset Investor Portfolio", filters={"fund": self.fund}, pluck="name")
		for pid in portfolios:
			port = frappe.get_doc("Asset Investor Portfolio", pid)
			port.recalculate_valuation(self.nav_per_unit)
			port.save(ignore_permissions=True)

		self.db_set("status", "Approved")

	def before_cancel(self) -> None:
		val_dt = getdate(self.valuation_date)
		later_val = frappe.db.get_value(
			"Asset Fund Valuation",
			{
				"fund": self.fund,
				"valuation_date": [">", val_dt],
				"status": "Approved",
				"docstatus": 1,
				"name": ["!=", self.name],
			},
			"name",
		)
		if later_val:
			frappe.throw(
				_(
					"Cannot cancel valuation {0} on {1} because a newer Approved valuation ({2}) exists. Only the latest valuation can be cancelled."
				).format(self.name, self.valuation_date, later_val),
				title=_("Latest Valuation Only"),
			)
		self.flags.ignore_links = True

	def on_cancel(self) -> None:
		"""Reverses GL, removes Asset Fund Price, and restores Fund cache."""
		val_dt = getdate(self.valuation_date)

		# 1. Reverse GL entries
		reverse_gl(self)

		# 2. Delete Asset Fund Price created by this valuation
		for fp_name in frappe.get_all(
			"Asset Fund Price",
			filters={"fund": self.fund, "price_date": val_dt},
			pluck="name",
		):
			frappe.db.delete("Asset Fund Price", {"name": fp_name})

		# 3. Restore Asset Fund display cache from prior approved valuation (if any)
		prev_val = self._get_previous_approved_valuation()
		fund = frappe.get_doc("Asset Fund", self.fund)
		if prev_val:
			prev_doc = frappe.get_doc("Asset Fund Valuation", prev_val.name)
			fund.current_nav_per_unit = flt(prev_doc.nav_per_unit, 6)
			fund.current_offer_price = flt(prev_doc.offer_price, 6)
			fund.current_bid_price = flt(prev_doc.bid_price, 6)
			fund.total_gav = flt(prev_doc.total_gav, 2)
			fund.total_nav = flt(prev_doc.total_nav, 2)
			fund.last_valuation_date = prev_doc.valuation_date
		else:
			fund.current_nav_per_unit = flt(fund.initial_nav_per_unit, 6)
			fund.current_offer_price = flt(fund.initial_nav_per_unit, 6)
			fund.current_bid_price = flt(fund.initial_nav_per_unit, 6)
			fund.last_valuation_date = None
		fund.save(ignore_permissions=True)

		self.db_set("status", "Cancelled")

	def _create_fund_price_record(self) -> None:
		val_dt = getdate(self.valuation_date)
		existing = frappe.db.get_value(
			"Asset Fund Price",
			{"fund": self.fund, "price_date": val_dt},
			"name",
		)
		if existing:
			frappe.db.delete("Asset Fund Price", {"name": existing})

		frappe.flags.in_valuation_submit = True
		try:
			fp = frappe.new_doc("Asset Fund Price")
			fp.fund = self.fund
			fp.price_date = val_dt
			fp.valuation = self.name
			fp.nav_per_unit = flt(self.nav_per_unit, 6)
			fp.bid_price = flt(self.bid_price, 6)
			fp.offer_price = flt(self.offer_price, 6)
			fp.insert(ignore_permissions=True)
		finally:
			frappe.flags.in_valuation_submit = False

	def _resolve_fee_expense_account(
		self, fund: Any, fee_type: str, custom_expense_account: str | None = None
	) -> str:
		if custom_expense_account and frappe.db.exists("Account", custom_expense_account):
			is_grp = frappe.db.get_value("Account", custom_expense_account, "is_group")
			if not is_grp:
				return custom_expense_account

		base_exp = getattr(fund, "fund_expenses_account", None)
		if base_exp and frappe.db.exists("Account", base_exp):
			is_grp = frappe.db.get_value("Account", base_exp, "is_group")
			if not is_grp:
				return base_exp

			# Create or fetch leaf expense account under the Fund Expenses group
			abbr = frappe.db.get_value("Company", fund.company, "abbr")
			leaf_label = f"{fee_type} Expense"
			existing_leaf = frappe.db.get_value(
				"Account",
				{"company": fund.company, "account_name": leaf_label, "is_group": 0},
				"name",
			) or frappe.db.get_value(
				"Account",
				{"company": fund.company, "name": f"{leaf_label} - {abbr}", "is_group": 0},
				"name",
			)
			if existing_leaf:
				return existing_leaf

			leaf_acc = frappe.new_doc("Account")
			leaf_acc.account_name = leaf_label
			leaf_acc.company = fund.company
			leaf_acc.parent_account = base_exp
			leaf_acc.root_type = "Expense"
			leaf_acc.is_group = 0
			leaf_acc.account_currency = fund.currency or frappe.db.get_value(
				"Company", fund.company, "default_currency"
			)
			leaf_acc.insert(ignore_permissions=True)
			return leaf_acc.name

		frappe.throw(
			_("Fund {0} is missing a configured Fund Expenses account.").format(fund.name),
			title=_("Missing Expense Account"),
		)
		return ""

	def get_gl_entries(self, fund: Any) -> list[dict[str, Any]]:
		"""Builds GL rows for daily valuation in the fund's Company:
		1. Dr each Fee Expense / Cr Fees Payable - Fund Manager
		2. Dr Interest Receivable / Cr Interest Income
		3. Mark-to-market change vs previous valuation: Dr/Cr Investment Revaluation vs Unrealised Gain/Loss
		"""
		if not fund.company:
			return []

		rows: list[dict[str, Any]] = []
		posting_date = str(self.valuation_date)

		# 1. Fee Accrual GL entries
		reg_label = (
			frappe.db.get_single_value("Fund Management Settings", "regulatory_fee_label") or "Regulatory Fee"
		)
		fee_items = [
			("Management Fee", Decimal(str(flt(self.management_fee_accrual, 2)))),
			("Custody Fee", Decimal(str(flt(self.custody_fee_accrual, 2)))),
			("Trustee Fee", Decimal(str(flt(self.trustee_fee_accrual, 2)))),
			(reg_label, Decimal(str(flt(self.cma_regulatory_fee_accrual, 2)))),
			("Audit Fee", Decimal(str(flt(self.audit_fee_accrual, 2)))),
		]
		rule_accounts = {f.fee_type: getattr(f, "expense_account", None) for f in getattr(fund, "fees", [])}
		total_fees = sum((amt for _, amt in fee_items), Decimal("0.00"))
		fees_payable_acc = getattr(fund, "fees_payable_account", None)

		if total_fees > Decimal("0.00") and fees_payable_acc:
			expense_accounts_used: list[str] = []
			for fee_type, amt in fee_items:
				if amt > Decimal("0.00"):
					exp_acc = self._resolve_fee_expense_account(fund, fee_type, rule_accounts.get(fee_type))
					expense_accounts_used.append(exp_acc)
					rows.append(
						{
							"company": fund.company,
							"account": exp_acc,
							"debit": amt,
							"credit": Decimal("0.00"),
							"against": fees_payable_acc,
							"posting_date": posting_date,
							"remarks": _("Daily {0} accrual for {1} on {2}").format(
								fee_type, self.fund, posting_date
							),
						}
					)

			rows.append(
				{
					"company": fund.company,
					"account": fees_payable_acc,
					"debit": Decimal("0.00"),
					"credit": total_fees,
					"against": ", ".join(sorted(set(expense_accounts_used))),
					"posting_date": posting_date,
					"remarks": _("Daily fees payable accrual for {0} on {1}").format(self.fund, posting_date),
				}
			)

		# 2. Interest Income Accrual GL entries
		daily_int = Decimal(str(flt(getattr(self, "daily_interest_accrual", 0.0), 2)))
		int_rec_acc = getattr(fund, "interest_receivable_account", None)
		int_inc_acc = getattr(fund, "interest_income_account", None)
		if daily_int > Decimal("0.00") and int_rec_acc and int_inc_acc:
			rows.append(
				{
					"company": fund.company,
					"account": int_rec_acc,
					"debit": daily_int,
					"credit": Decimal("0.00"),
					"against": int_inc_acc,
					"posting_date": posting_date,
					"remarks": _("Daily interest receivable accrual for {0} on {1}").format(
						self.fund, posting_date
					),
				}
			)
			rows.append(
				{
					"company": fund.company,
					"account": int_inc_acc,
					"debit": Decimal("0.00"),
					"credit": daily_int,
					"against": int_rec_acc,
					"posting_date": posting_date,
					"remarks": _("Daily interest income accrual for {0} on {1}").format(
						self.fund, posting_date
					),
				}
			)

		# 3. Mark-to-Market Revaluation Change vs Previous Valuation
		mtm_change = Decimal(str(flt(getattr(self, "mtm_revaluation_change", 0.0), 2)))
		inv_reval_acc = getattr(fund, "investment_revaluation_account", None)
		unrealised_acc = getattr(fund, "unrealised_gain_loss_account", None)
		if mtm_change != Decimal("0.00") and inv_reval_acc and unrealised_acc:
			if mtm_change > Decimal("0.00"):
				rows.append(
					{
						"company": fund.company,
						"account": inv_reval_acc,
						"debit": mtm_change,
						"credit": Decimal("0.00"),
						"against": unrealised_acc,
						"posting_date": posting_date,
						"remarks": _("Mark-to-market revaluation gain for {0} on {1}").format(
							self.fund, posting_date
						),
					}
				)
				rows.append(
					{
						"company": fund.company,
						"account": unrealised_acc,
						"debit": Decimal("0.00"),
						"credit": mtm_change,
						"against": inv_reval_acc,
						"posting_date": posting_date,
						"remarks": _("Mark-to-market revaluation gain for {0} on {1}").format(
							self.fund, posting_date
						),
					}
				)
			else:
				loss_amt = abs(mtm_change)
				rows.append(
					{
						"company": fund.company,
						"account": unrealised_acc,
						"debit": loss_amt,
						"credit": Decimal("0.00"),
						"against": inv_reval_acc,
						"posting_date": posting_date,
						"remarks": _("Mark-to-market revaluation loss for {0} on {1}").format(
							self.fund, posting_date
						),
					}
				)
				rows.append(
					{
						"company": fund.company,
						"account": inv_reval_acc,
						"debit": Decimal("0.00"),
						"credit": loss_amt,
						"against": unrealised_acc,
						"posting_date": posting_date,
						"remarks": _("Mark-to-market revaluation loss for {0} on {1}").format(
							self.fund, posting_date
						),
					}
				)

		return rows
