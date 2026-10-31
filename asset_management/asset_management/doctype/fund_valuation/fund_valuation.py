import frappe
from frappe.model.document import Document
from frappe.utils import flt

class FundValuation(Document):
    def validate(self):
        self.calculate_nav()

    def calculate_nav(self):
        """
        Replicates NAV calculation logic from BC FundValuation.Codeunit.al:
        1. Evaluates all line items (quantity * market_price + accrued_interest)
        2. Computes Gross NAV
        3. Deducts expenses to arrive at Closing Net Asset Value (NAV)
        4. Calculates NAV Per Unit based on total outstanding units
        """
        gross_val = 0.0
        for line in self.valuation_lines:
            line_val = (flt(line.quantity) * flt(line.market_price)) + flt(line.accrued_interest)
            line.current_value = round(line_val, 2)
            gross_val += line_val

        self.gross_nav = round(gross_val, 2)
        expenses = flt(self.total_expenses)
        self.closing_nav = round(self.gross_nav - expenses, 2)

        units = flt(self.total_outstanding_units)
        if units > 0:
            self.nav_per_unit = round(self.closing_nav / units, 4)
        else:
            self.nav_per_unit = 0.0
