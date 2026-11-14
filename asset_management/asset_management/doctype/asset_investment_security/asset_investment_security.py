import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, date_diff, flt, getdate


class AssetInvestmentSecurity(Document):
	def validate(self):
		if not self.currency:
			self.currency = frappe.db.get_single_value("System Settings", "currency") or "USD"
		if self.issue_date and self.maturity_date:
			self.tenor_days = date_diff(self.maturity_date, self.issue_date)

		# Auto-generate coupon schedule for bonds if empty
		if (
			self.asset_class in ("Treasury Bond", "Corporate Bond")
			and self.coupon_rate
			and self.issue_date
			and self.maturity_date
		):
			if not self.coupon_schedule:
				self.generate_coupon_schedule()

	def generate_coupon_schedule(self):
		"""Generates periodic coupon dates and cash flows until maturity."""
		self.coupon_schedule = []
		months_step = (
			6 if self.coupon_frequency == "Semi-Annual" else (12 if self.coupon_frequency == "Annual" else 3)
		)
		periodic_rate = flt(self.coupon_rate) / (12.0 / months_step)

		curr_date = getdate(self.issue_date)
		mat_date = getdate(self.maturity_date)
		period = 1

		while curr_date < mat_date:
			next_date = add_months(curr_date, months_step)
			if next_date > mat_date:
				next_date = mat_date

			# Cash flow per 100 face value
			cash_flow = round(100.0 * (periodic_rate / 100.0), 4)

			self.append(
				"coupon_schedule",
				{
					"coupon_number": period,
					"coupon_date": next_date,
					"coupon_rate": periodic_rate,
					"coupon_amount": cash_flow,
					"received": 0,
				},
			)
			curr_date = next_date
			period += 1
