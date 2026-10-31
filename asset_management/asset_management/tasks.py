# Tasks for Asset Management

import frappe
from frappe.utils import nowdate

def calculate_nav():
    """Daily NAV calculation for all active investment portfolios.
    This function iterates over `Fund Valuation` records in draft status,
    invokes the controller method `calculate_nav` on each document, and
    submits the valuation.
    """
    valuations = frappe.get_all('Fund Valuation', filters={'docstatus': 0})
    for v in valuations:
        doc = frappe.get_doc('Fund Valuation', v.name)
        try:
            doc.calculate_nav()
            doc.submit()
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"NAV calculation failed for {v.name}: {e}")

def process_dividends():
    """Daily dividend declaration processing.
    Finds dividend declarations scheduled for today, calculates amounts
    using the controller logic, and submits them.
    """
    today = nowdate()
    decls = frappe.get_all('Dividend Declaration', filters={
        'declaration_date': today,
        'docstatus': 0
    })
    for d in decls:
        doc = frappe.get_doc('Dividend Declaration', d.name)
        try:
            doc.calculate_dividends()
            doc.submit()
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(f"Dividend processing failed for {d.name}: {e}")
