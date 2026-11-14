import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class AssetFundPrice(Document):
	def validate(self) -> None:
		if not getattr(frappe.flags, "in_valuation_submit", False):
			if not self.valuation or not frappe.db.exists("Asset Fund Valuation", self.valuation):
				frappe.throw(
					_(
						"Asset Fund Price can only be created by submitting an Asset Fund Valuation."
					),
					title=_("Direct Creation Not Permitted"),
				)

		if flt(self.nav_per_unit, 6) <= 0 or flt(self.bid_price, 6) <= 0 or flt(self.offer_price, 6) <= 0:
			frappe.throw(
				_("NAV per unit, Bid Price, and Offer Price must all be greater than zero."),
				title=_("Invalid Fund Price"),
			)

		existing = frappe.db.get_value(
			"Asset Fund Price",
			{
				"fund": self.fund,
				"price_date": getdate(self.price_date),
				"name": ["!=", self.name or ""],
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("An Asset Fund Price ({0}) already exists for fund {1} on {2}.").format(
					existing, self.fund, self.price_date
				),
				title=_("Duplicate Fund Price"),
			)
