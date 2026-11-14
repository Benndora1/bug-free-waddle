from datetime import timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import getdate

from asset_management.services.reconciliation import reconcile_fund


def execute(
	filters: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
	filters = filters or {}

	columns = [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
		{
			"label": _("Fund"),
			"fieldname": "fund",
			"fieldtype": "Link",
			"options": "Asset Fund",
			"width": 120,
		},
		{
			"label": _("Units in Issue"),
			"fieldname": "units_in_issue",
			"fieldtype": "Float",
			"precision": 6,
			"width": 140,
		},
		{
			"label": _("NAV per Unit"),
			"fieldname": "nav_per_unit",
			"fieldtype": "Float",
			"precision": 6,
			"width": 130,
		},
		{
			"label": _("Register Value"),
			"fieldname": "register_value",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": _("GL Net Assets"),
			"fieldname": "gl_net_assets",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": _("Difference"),
			"fieldname": "difference",
			"fieldtype": "Currency",
			"width": 130,
		},
		{
			"label": _("Within Tolerance"),
			"fieldname": "within_tolerance",
			"fieldtype": "Check",
			"width": 120,
		},
		{
			"label": _("Status"),
			"fieldname": "status",
			"fieldtype": "Data",
			"width": 130,
		},
	]

	fund = filters.get("fund")
	from_date_str = filters.get("from_date") or filters.get("from")
	to_date_str = filters.get("to_date") or filters.get("to")

	funds: list[str] = (
		[fund] if fund else frappe.get_all("Asset Fund", filters={"status": "Active"}, pluck="name")
	)

	data: list[dict[str, Any]] = []
	for f_code in funds:
		if from_date_str and to_date_str:
			cur = getdate(from_date_str)
			end = getdate(to_date_str)
			dates_to_check: list[str] = []
			while cur <= end:
				dates_to_check.append(str(cur))
				cur += timedelta(days=1)
		else:
			price_dates = frappe.get_all(
				"Asset Fund Price",
				filters={"fund": f_code},
				pluck="price_date",
				order_by="price_date asc",
			)
			dates_to_check = [str(d) for d in price_dates]

		for d_str in dates_to_check:
			rec = reconcile_fund(f_code, d_str)
			is_ok = bool(rec["within_tolerance"])
			data.append(
				{
					"date": rec["date"],
					"fund": f_code,
					"units_in_issue": float(rec["units_in_issue"]),
					"nav_per_unit": float(rec["nav_per_unit"]),
					"register_value": float(rec["register_value"]),
					"gl_net_assets": float(rec["gl_net_assets"]),
					"difference": float(rec["difference"]),
					"within_tolerance": 1 if is_ok else 0,
					"status": _("Reconciled") if is_ok else _("Failed"),
				}
			)

	return columns, data
