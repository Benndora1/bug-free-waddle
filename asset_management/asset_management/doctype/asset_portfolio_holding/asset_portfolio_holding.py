import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

class AssetPortfolioHolding(Document):
    def validate(self):
        self.recalculate_values()

    def recalculate_values(self):
        """Recalculates dirty market value and carrying costs."""
        self.face_value = round(flt(self.face_value), 2)
        self.carrying_cost = round(flt(self.carrying_cost), 2)
        self.accrued_interest = round(flt(self.accrued_interest), 2)

        if not self.dirty_market_value or self.dirty_market_value == 0:
            self.dirty_market_value = round(self.carrying_cost + self.accrued_interest, 2)
        if not self.amortized_cost or self.amortized_cost == 0:
            self.amortized_cost = self.carrying_cost
