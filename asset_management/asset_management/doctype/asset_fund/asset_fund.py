# Copyright (c) 2024, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AssetFund(Document):
	def validate(self):
		"""Validates fund setup."""
		if not getattr(self, "fund_name", None):
			frappe.throw(_("Fund Name is mandatory."))

		m_rate = getattr(self, "management_fee_rate", None)
		if m_rate is not None and m_rate < 0:
			frappe.throw(_("Management Fee Rate cannot be negative."))

		er_rate = getattr(self, "early_redemption_fee_rate", None)
		if er_rate is not None and er_rate < 0:
			frappe.throw(_("Early Redemption Fee Rate cannot be negative."))

		# Per Task R-07: Status cannot become "Active" until all account fields are configured
		if self.status == "Active" and not (frappe.flags.in_import or frappe.flags.in_fixtures):
			account_keys = [
				"client_cash_payable_account",
				"unallocated_receipts_account",
				"unitholders_capital_account",
				"entry_fee_payable_account",
				"exit_fee_payable_account",
				"wht_payable_account",
				"fees_payable_account",
				"due_to_other_funds_account",
				"due_from_other_funds_account",
				"interest_receivable_account",
				"investments_at_cost_account",
				"investment_revaluation_account",
				"interest_income_account",
				"unrealised_gain_loss_account",
				"realised_gain_loss_account",
				"fund_expenses_account",
				"rounding_account",
			]
			missing = [k for k in account_keys if not getattr(self, k, None)]
			if missing:
				frappe.throw(
					_(
						"Fund {0} cannot become Active until all accounting fields are configured. Missing: {1}. Click 'Set up Accounts' to configure."
					).format(self.name, ", ".join(missing)),
					title=_("Incomplete Fund Accounting Setup"),
				)

	def update_units_in_issue(self, delta_units):
		"""Updates units in issue and recalculates total NAV."""
		self.total_units_in_issue = round(
			max(0.0, (getattr(self, "total_units_in_issue", 0.0) or 0.0) + delta_units), 4
		)
		self.total_nav = round(
			self.total_units_in_issue * (getattr(self, "current_nav_per_unit", 0.0) or 0.0), 2
		)
