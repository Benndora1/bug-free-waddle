import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class AssetSecurityPrice(Document):
	def validate(self) -> None:
		# Support callers passing `yield` in dict/attribute
		raw_yield = self.__dict__.get("yield")
		if raw_yield is not None and not self.yield_rate:
			self.yield_rate = flt(raw_yield, 6)

		if flt(self.clean_price, 6) <= 0:
			frappe.throw(
				_("Clean Price must be greater than zero for security {0}.").format(self.security),
				title=_("Invalid Security Price"),
			)

		existing = frappe.db.get_value(
			"Asset Security Price",
			{
				"security": self.security,
				"price_date": getdate(self.price_date),
				"name": ["!=", self.name or ""],
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("An Asset Security Price ({0}) already exists for security {1} on {2}.").format(
					existing, self.security, self.price_date
				),
				title=_("Duplicate Security Price"),
			)

	def on_update(self) -> None:
		if self.security and frappe.db.exists("Asset Investment Security", self.security):
			frappe.db.set_value(
				"Asset Investment Security",
				self.security,
				"current_market_price",
				flt(self.clean_price, 6),
			)
