import frappe
from frappe import _
from frappe.model.document import Document


class AssetCustodyInstruction(Document):
	def before_submit(self):
		"""Enforces dual maker-checker signatures before dispatch to Stanbic Custody."""
		if not self.maker_signed:
			frappe.throw(
				_(
					"Custody Instruction {0} must be signed by the Operations Maker (maker_signed = 1) before submission."
				).format(self.name)
			)
		if not self.checker_signed:
			frappe.throw(
				_(
					"Custody Instruction {0} must be signed by the Investment Manager Checker (checker_signed = 1) before submission."
				).format(self.name)
			)
		if self.maker_signatory and self.checker_signatory and self.maker_signatory == self.checker_signatory:
			frappe.throw(
				_(
					"Dual control violation: Primary and Secondary Signatories cannot be the same user for Custody Instruction {0}."
				).format(self.name)
			)

	def on_submit(self):
		"""Dispatches custody instruction and marks trade order settled."""
		self.db_set("status", "Authorized & Dispatched")
		if self.trade_order:
			frappe.db.set_value("Asset Trade Order Header", self.trade_order, "status", "Settled")

	def on_cancel(self):
		self.db_set("status", "Cancelled")
