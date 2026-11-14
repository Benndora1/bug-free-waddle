import frappe
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class AssetAgentCommission(Document):
	def validate(self):
		if not self.posting_date:
			self.posting_date = nowdate()
		if self.gross_subscription_amount and self.commission_rate_pct:
			self.commission_amount = round(
				flt(self.gross_subscription_amount) * (flt(self.commission_rate_pct) / 100.0), 2
			)
