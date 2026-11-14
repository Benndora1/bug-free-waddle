"""Controller for Asset Unit Ledger Entry."""

import frappe
from frappe import _
from frappe.model.document import Document


class AssetUnitLedgerEntry(Document):
	def validate(self):
		"""Enforces immutability: unit ledger entries cannot have their critical fields modified once inserted."""
		if not self.is_new():
			for field in ("investor", "fund", "voucher_type", "voucher_no", "units", "price_per_unit"):
				if self.has_value_changed(field):
					frappe.throw(
						_("Cannot edit field '{0}' on immutable Asset Unit Ledger Entry {1}.").format(
							field, self.name
						)
					)

	def on_trash(self):
		"""Enforces immutability: unit ledger entries can only be reversed via is_cancelled, never deleted."""
		frappe.throw(
			_(
				"Cannot delete immutable Asset Unit Ledger Entry {0}. Cancel the source voucher instead."
			).format(self.name)
		)
