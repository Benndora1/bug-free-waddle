import frappe
from frappe.model.document import Document
from frappe.utils import flt

class DividendDeclaration(Document):
    def validate(self):
        self.calculate_dividends()

    def calculate_dividends(self):
        """
        Calculates gross dividend, WHT deduction, and net dividend for all qualified investors.
        """
        rate = flt(self.dividend_per_unit)
        wht_pct = flt(self.withholding_tax_pct) / 100.0

        total_gross = 0.0
        total_net = 0.0

        for line in self.dividend_lines:
            units = flt(line.units_held)
            gross = units * rate
            wht = gross * wht_pct
            net = gross - wht

            line.gross_dividend = round(gross, 2)
            line.withholding_tax = round(wht, 2)
            line.net_dividend_payable = round(net, 2)

            total_gross += gross
            total_net += net

        self.total_gross_dividend = round(total_gross, 2)
        self.total_net_dividend = round(total_net, 2)
