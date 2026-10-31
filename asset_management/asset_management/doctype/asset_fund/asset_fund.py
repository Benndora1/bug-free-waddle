import frappe
from frappe import _
from frappe.model.document import Document

class AssetFund(Document):
    def validate(self):
        if not self.initial_nav_per_unit or self.initial_nav_per_unit <= 0:
            self.initial_nav_per_unit = 100.0
            
        if not self.current_nav_per_unit or self.current_nav_per_unit <= 0:
            self.current_nav_per_unit = self.initial_nav_per_unit

        spread = (self.bid_offer_spread_pct or 0.0) / 100.0
        self.current_offer_price = round(self.current_nav_per_unit * (1.0 + spread), 4)
        self.current_bid_price = round(self.current_nav_per_unit * (1.0 - spread), 4)

        if self.total_units_in_issue is None:
            self.total_units_in_issue = 0.0

        self.total_nav = round(self.total_units_in_issue * self.current_nav_per_unit, 2)
        if not self.total_gav:
            self.total_gav = self.total_nav

    def update_units_in_issue(self, delta_units):
        """Updates units in issue and recalculates total NAV."""
        self.total_units_in_issue = round(max(0.0, (self.total_units_in_issue or 0.0) + delta_units), 4)
        self.total_nav = round(self.total_units_in_issue * self.current_nav_per_unit, 2)
        self.db_set("total_units_in_issue", self.total_units_in_issue)
        self.db_set("total_nav", self.total_nav)
