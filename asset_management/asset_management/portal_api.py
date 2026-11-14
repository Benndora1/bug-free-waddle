import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, today


def get_resolved_investor(investor=None):
	"""
	Resolve the current Asset Investor from session user or explicit parameter.
	If session user matches investor email, returns that investor.
	For Administrator / System Manager, allows explicit parameter or falls back to first active investor.
	"""
	if investor and frappe.db.exists("Asset Investor", investor):
		return investor

	user = frappe.session.user
	if user and user != "Guest":
		matched = frappe.db.get_value("Asset Investor", {"email": user}, "name")
		if matched:
			return matched

	# Fallback for admin / desk testing
	if user in ["Administrator", "root"] or "System Manager" in frappe.get_roles():
		first = frappe.db.get_value("Asset Investor", {"status": "Active"}, "name")
		if first:
			return first

	return None


def get_resolved_agent(agent=None):
	"""
	Resolve the current Asset Agent from session user or explicit parameter.
	"""
	if agent and frappe.db.exists("Asset Agent", agent):
		return agent

	user = frappe.session.user
	if user and user != "Guest":
		matched = frappe.db.get_value("Asset Agent", {"email": user}, "name")
		if matched:
			return matched

	if user in ["Administrator", "root"] or "System Manager" in frappe.get_roles():
		first = frappe.db.get_value("Asset Agent", {"status": "Active"}, "name")
		if first:
			return first

	return None


@frappe.whitelist()
def get_investor_dashboard(investor=None):
	"""
	Returns full dashboard data for the Investor Self-Service Portal:
	- Investor Profile details
	- Summary Metrics (Total Value, Total Units, Unrealized Gain)
	- Fund Portfolios Breakdown
	- Recent Subscriptions, Redemptions & Switches
	- Market Funds Overview (Current NAVs)
	"""
	investor_id = get_resolved_investor(investor)
	if not investor_id:
		return {"error": "Investor profile not found. Please log in or provide investor ID."}

	inv = frappe.get_doc("Asset Investor", investor_id)

	# Portfolios
	portfolios = frappe.get_all(
		"Asset Investor Portfolio",
		filters={"investor": investor_id},
		fields=[
			"name",
			"fund",
			"fund_name",
			"portfolio_status",
			"currency",
			"total_units",
			"current_nav_per_unit",
			"current_market_value",
			"total_invested_amount",
			"total_withdrawn_amount",
			"unrealized_gain_loss",
		],
	)

	total_value = sum(flt(p.current_market_value) for p in portfolios)
	total_units = sum(flt(p.total_units) for p in portfolios)
	total_invested = sum(flt(p.total_invested_amount) for p in portfolios)
	total_unrealized = sum(flt(p.unrealized_gain_loss) for p in portfolios)

	# Recent Subscriptions
	recent_subs = frappe.get_all(
		"Asset Subscription",
		filters={"investor": investor_id},
		fields=[
			"name",
			"subscription_date",
			"fund",
			"gross_amount",
			"units_allocated",
			"status",
			"docstatus",
		],
		order_by="creation desc",
		limit=5,
	)

	# Recent Redemptions
	recent_reds = frappe.get_all(
		"Asset Redemption",
		filters={"investor": investor_id},
		fields=[
			"name",
			"redemption_date",
			"fund",
			"net_payout_amount",
			"units_to_redeem",
			"status",
			"docstatus",
		],
		order_by="creation desc",
		limit=5,
	)

	# Available Funds in Market
	market_funds = frappe.get_all(
		"Asset Fund",
		filters={"status": "Active"},
		fields=[
			"name",
			"fund_id",
			"fund_name",
			"fund_type",
			"currency",
			"current_nav_per_unit",
			"current_offer_price",
			"current_bid_price",
			"last_valuation_date",
			"prior_day_valuation_approved",
		],
		order_by="fund_name asc",
	)

	return {
		"investor": {
			"name": inv.name,
			"investor_name": inv.investor_name,
			"investor_type": inv.investor_type,
			"tax_id": inv.tax_id,
			"email": inv.email,
			"telephone": inv.phone if hasattr(inv, "phone") else "",
			"country": inv.country_of_residence if hasattr(inv, "country_of_residence") else "",
			"risk_rating": inv.risk_tier if hasattr(inv, "risk_tier") else "",
			"status": inv.status,
		},
		"total_value": total_value,
		"total_units": total_units,
		"total_invested": total_invested,
		"total_unrealized": total_unrealized,
		"portfolios": portfolios,
		"recent_subscriptions": recent_subs,
		"recent_redemptions": recent_reds,
		"market_funds": market_funds,
	}


@frappe.whitelist()
def get_investor_holdings(investor=None):
	"""
	Returns investor's portfolio holdings breakdown with detailed metrics.
	"""
	investor_id = get_resolved_investor(investor)
	if not investor_id:
		return {"error": "Investor profile not found."}

	inv = frappe.get_doc("Asset Investor", investor_id)
	portfolios = frappe.get_all(
		"Asset Investor Portfolio",
		filters={"investor": investor_id},
		fields=[
			"name",
			"fund",
			"fund_name",
			"currency",
			"portfolio_status",
			"first_subscription_date",
			"last_transaction_date",
			"total_units",
			"current_nav_per_unit",
			"current_market_value",
			"total_invested_amount",
			"total_withdrawn_amount",
			"unrealized_gain_loss",
		],
	)

	# Calculate holding metrics
	for p in portfolios:
		units = flt(p.total_units)
		cost = flt(p.total_invested_amount) - flt(p.total_withdrawn_amount)
		avg_cost = (cost / units) if units > 0 else 0.0
		p["avg_cost"] = avg_cost
		val = flt(p.current_market_value)
		p["gain_pct"] = ((val - cost) / cost * 100.0) if cost > 0 else 0.0

	return {
		"investor": inv.as_dict(),
		"portfolios": portfolios,
		"total_value": sum(flt(p.current_market_value) for p in portfolios),
		"total_units": sum(flt(p.total_units) for p in portfolios),
	}


@frappe.whitelist()
def get_investor_statement(investor=None, from_date=None, to_date=None, fund=None):
	"""
	Returns the unit transaction ledger statement from Asset Investor Register Line.
	"""
	investor_id = get_resolved_investor(investor)
	if not investor_id:
		return {"error": "Investor profile not found."}

	filters = {"investor": investor_id}
	if fund:
		filters["fund"] = fund
	if from_date:
		filters["posting_date"] = [">=", from_date]
	if to_date:
		if "posting_date" in filters:
			filters["posting_date"] = ["between", [from_date, to_date]]
		else:
			filters["posting_date"] = ["<=", to_date]

	lines = frappe.get_all(
		"Asset Investor Register Line",
		filters=filters,
		fields=[
			"name",
			"posting_date",
			"value_date",
			"fund",
			"entry_type",
			"voucher_type",
			"voucher_no",
			"units",
			"nav_per_unit",
			"running_unit_balance",
			"gross_amount",
			"fees",
			"net_amount",
		],
		order_by="posting_date asc, creation asc",
	)

	inv = frappe.get_doc("Asset Investor", investor_id)
	return {
		"investor": inv.as_dict(),
		"lines": lines,
		"filter_fund": fund,
		"from_date": from_date,
		"to_date": to_date,
	}


@frappe.whitelist()
def submit_online_subscription(
	investor, fund, amount, payment_reference=None, payment_mode="Bank Transfer / BOL"
):
	"""
	Creates an online subscription request in Draft (docstatus=0).
	Requires operations maker-checker approval to submit and allocate units.
	"""
	investor_id = get_resolved_investor(investor)
	if not investor_id:
		frappe.throw(_("Invalid or unauthorized investor."))

	if not frappe.db.exists("Asset Fund", fund):
		frappe.throw(_("Invalid fund specified."))

	amount = flt(amount)
	if amount <= 0:
		frappe.throw(_("Subscription amount must be positive."))

	fund_doc = frappe.get_doc("Asset Fund", fund)
	if fund_doc.status != "Active":
		frappe.throw(_("Fund {0} is currently inactive.").format(fund))

	# Min subscription check
	min_sub = flt(getattr(fund_doc, "min_subscription_amount", 0.0))
	if min_sub > 0 and amount < min_sub:
		has_portfolio = frappe.db.exists("Asset Investor Portfolio", {"investor": investor_id, "fund": fund})
		min_add = flt(getattr(fund_doc, "min_additional_amount", 0.0))
		if has_portfolio:
			if min_add > 0 and amount < min_add:
				frappe.throw(
					_("Amount is below minimum additional subscription of {0:,.2f} {1}").format(
						min_add, fund_doc.currency
					)
				)
		else:
			frappe.throw(
				_("Amount is below minimum initial subscription of {0:,.2f} {1}").format(
					min_sub, fund_doc.currency
				)
			)

	inv_doc = frappe.get_doc("Asset Investor", investor_id)

	sub = frappe.new_doc("Asset Subscription")
	sub.investor = investor_id
	sub.fund = fund
	sub.subscription_date = today()
	sub.value_date = today()
	sub.currency = fund_doc.currency
	sub.payment_method = payment_mode or "Bank Transfer / BOL"
	sub.bank_reference = payment_reference or "ONLINE-PORTAL-SUB"
	sub.gross_amount = amount
	sub.status = "Draft"
	sub.agent = inv_doc.agent if hasattr(inv_doc, "agent") else None
	sub.insert(ignore_permissions=True)

	return {
		"success": True,
		"subscription": sub.name,
		"message": _("Subscription request {0} submitted successfully for review.").format(sub.name),
	}


@frappe.whitelist()
def submit_online_redemption(
	investor, fund, redemption_by="Amount", requested_amount=0, requested_units=0, bank_account=None
):
	"""
	Creates an online redemption request in Draft (docstatus=0).
	Enforces Foundational Rule 1 (Prior-Day Valuation Guard) and holdings check.
	"""
	investor_id = get_resolved_investor(investor)
	if not investor_id:
		frappe.throw(_("Invalid or unauthorized investor."))

	if not frappe.db.exists("Asset Fund", fund):
		frappe.throw(_("Invalid fund specified."))

	portfolio_name = frappe.db.get_value(
		"Asset Investor Portfolio", {"investor": investor_id, "fund": fund}, "name"
	)
	if not portfolio_name:
		frappe.throw(_("You do not hold an active portfolio in fund {0}.").format(fund))

	portfolio = frappe.get_doc("Asset Investor Portfolio", portfolio_name)
	avail_units = flt(portfolio.total_units)

	if avail_units <= 0:
		frappe.throw(_("You have zero available units in fund {0}.").format(fund))

	fund_doc = frappe.get_doc("Asset Fund", fund)

	# Foundational Rule 1: Prior-Day Valuation Guard
	if not fund_doc.prior_day_valuation_approved:
		frappe.throw(
			_(
				"Rule 1 Violation: Prior-day valuation has not been approved for {0}. Redemptions are restricted until daily valuation is completed."
			).format(fund)
		)

	red = frappe.new_doc("Asset Redemption")
	red.investor = investor_id
	red.fund = fund
	red.portfolio = portfolio_name
	red.redemption_date = today()
	red.value_date = today()
	red.currency = fund_doc.currency
	red.prior_day_valuation_approved = 1 if fund_doc.prior_day_valuation_approved else 0
	red.redemption_by = redemption_by
	red.requested_amount = flt(requested_amount)
	red.requested_units = flt(requested_units)
	red.status = "Draft"
	red.insert(ignore_permissions=True)

	return {
		"success": True,
		"redemption": red.name,
		"message": _("Redemption request {0} submitted successfully for review.").format(red.name),
	}


@frappe.whitelist()
def get_agent_dashboard(agent=None):
	"""
	Returns full dashboard data for the Agent Distribution Portal:
	- Agent Profile
	- Total Linked Clients
	- Total Commissions Accrued and Paid
	- Commission Ledger
	- Client Directory
	"""
	agent_id = get_resolved_agent(agent)
	if not agent_id:
		return {"error": "Agent profile not found. Please log in or provide agent code."}

	ag = frappe.get_doc("Asset Agent", agent_id)

	# Linked Investors through Subscriptions
	linked_investor_ids = frappe.get_all(
		"Asset Subscription", filters={"agent": ag.agent_code}, pluck="investor", distinct=True
	)

	clients = []
	if linked_investor_ids:
		clients = frappe.get_all(
			"Asset Investor",
			filters={"name": ["in", linked_investor_ids]},
			fields=["name", "investor_name", "investor_type", "status", "risk_tier", "phone", "email"],
			order_by="creation desc",
		)

	# Commissions
	commissions = frappe.get_all(
		"Asset Agent Commission",
		filters={"agent": ag.agent_code},
		fields=[
			"name",
			"subscription",
			"posting_date",
			"investor",
			"fund",
			"gross_subscription_amount",
			"commission_rate_pct",
			"commission_amount",
			"payment_status",
			"payment_reference",
		],
		order_by="posting_date desc",
	)

	total_earned = sum(flt(c.commission_amount) for c in commissions)
	total_paid = sum(flt(c.commission_amount) for c in commissions if c.payment_status == "Paid")
	unpaid = total_earned - total_paid

	return {
		"agent": {
			"name": ag.name,
			"agent_code": ag.agent_code,
			"agent_name": ag.agent_name,
			"agent_type": ag.agent_type,
			"status": ag.status,
			"commission_rate": ag.commission_rate_pct,
			"email": ag.email,
			"phone": ag.phone,
			"license_no": ag.license_no,
		},
		"total_clients": len(clients),
		"total_commission_earned": total_earned,
		"total_commission_paid": total_paid,
		"commission_due": unpaid,
		"clients": clients,
		"commissions": commissions,
	}
