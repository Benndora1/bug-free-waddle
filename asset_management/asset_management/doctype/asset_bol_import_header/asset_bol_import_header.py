import csv
import io

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime, nowdate, time_diff_in_hours


class AssetBOLImportHeader(Document):
	def validate(self):
		if not self.import_date:
			self.import_date = nowdate()
		self.recompute_totals()

	def recompute_totals(self):
		total_amt = 0.0
		matched = 0
		exceptions = 0
		if self.lines:
			for l in self.lines:
				total_amt += flt(l.amount)
				if l.status in ("Matched", "Subscription Created"):
					matched += 1
				elif l.status == "Exception":
					exceptions += 1
			self.total_lines = len(self.lines)
			self.total_amount = round(total_amt, 2)
			self.matched_lines = matched
			self.exception_lines = exceptions

	@frappe.whitelist()
	def parse_bol_statement(self, csv_content):
		"""Parses BOL statement CSV reproducing BOLImportProcessing.Codeunit.al."""
		if isinstance(csv_content, bytes):
			csv_content = csv_content.decode("utf-8", errors="ignore")

		f = io.StringIO(csv_content.strip())
		reader = csv.reader(f)

		self.lines = []
		line_no = 1
		data_started = False

		# Pre-load investors for fast matching
		all_investors = frappe.get_all(
			"Asset Investor",
			fields=["name", "investor_name", "investor_id", "tax_id", "bank_account_no", "phone"],
		)

		for row in reader:
			if not row or not any(cell.strip() for cell in row):
				continue

			first_cell = row[0].strip().lower()
			if "value date" in first_cell or "date" in first_cell:
				data_started = True
				continue

			if not data_started and len(row) < 3:
				# Header metadata rows
				continue

			# Template: Value Date, Transaction Description, Amount, Fund Code
			val_date_str = row[0].strip() if len(row) > 0 else ""
			desc = row[1].strip() if len(row) > 1 else ""
			amt_str = row[2].strip().replace(",", "") if len(row) > 2 else "0"
			fund_code = row[3].strip() if len(row) > 3 else "SBG-MMF"

			try:
				amt = float(amt_str)
			except ValueError:
				amt = 0.0

			val_date = self.import_date
			if val_date_str:
				try:
					val_date = getdate(val_date_str)
				except Exception:
					val_date = self.import_date

			matched_inv = None
			match_method = "None"
			desc_upper = desc.upper()

			# Client matching heuristic (Codeunit 51404503 DetectAndMatch)
			for inv in all_investors:
				# 1. Match by Identification / Investor ID or Tax ID
				if inv.investor_id and inv.investor_id.upper() in desc_upper:
					matched_inv = inv
					match_method = "Investor ID Match"
					break
				if inv.tax_id and inv.tax_id.upper() in desc_upper:
					matched_inv = inv
					match_method = "Investor ID Match"
					break
				# 2. Match by Bank Account Number
				if inv.bank_account_no and len(inv.bank_account_no) > 5 and inv.bank_account_no in desc:
					matched_inv = inv
					match_method = "Bank Account Match"
					break
				# 3. Match by Phone Number
				if inv.phone and len(inv.phone) > 6 and inv.phone in desc:
					matched_inv = inv
					match_method = "Phone Match"
					break

			# Resolve Fund Link
			fund_link = None
			if frappe.db.exists("Asset Fund", fund_code):
				fund_link = fund_code
			elif frappe.db.exists("Asset Fund", "SBG-MMF"):
				fund_link = "SBG-MMF"

			status = "Matched" if (matched_inv and amt > 0) else "Exception"
			exc_reason = ""
			if not matched_inv:
				exc_reason = f"No matching investor account found for narration: '{desc}'"
			elif amt <= 0:
				exc_reason = f"Invalid transaction amount: {amt}"

			self.append(
				"lines",
				{
					"line_no": line_no,
					"value_date": val_date,
					"transaction_description": desc,
					"amount": amt,
					"fund_code": fund_code,
					"fund": fund_link,
					"matched_investor": matched_inv.name if matched_inv else None,
					"matched_investor_name": matched_inv.investor_name if matched_inv else None,
					"match_method": match_method,
					"status": status,
					"exception_reason": exc_reason,
					"unallocated_since": val_date if status == "Exception" else None,
					"unallocated_hours": 0.0,
					"escalated_to_supervisor": 0,
				},
			)
			line_no += 1

		self.status = "Imported"
		self.recompute_totals()
		self.save(ignore_permissions=True)

	@frappe.whitelist()
	def check_unallocated_sla(self, threshold_hours=48.0):
		"""Monitors 48-hour unallocated SLA per Operational Procedures Manual Section 4.10."""
		escalations = 0
		now_dt = now_datetime()
		for l in self.lines:
			if l.status == "Exception" and l.unallocated_since:
				# Compute hours elapsed
				since_dt = getdate(l.unallocated_since)
				hrs = time_diff_in_hours(now_dt, since_dt)
				l.unallocated_hours = round(hrs, 1)
				if hrs >= float(threshold_hours):
					l.escalated_to_supervisor = 1
					escalations += 1
					# Log suspicious / unallocated transaction event
					if not frappe.db.exists(
						"Asset Suspicious Transaction Log",
						{"transaction_reference": f"{self.name}-{l.line_no}"},
					):
						log = frappe.new_doc("Asset Suspicious Transaction Log")
						log.log_date = nowdate()
						log.rule = "AML_UNALLOCATED"
						log.transaction_reference = f"{self.name}-{l.line_no}"
						log.amount = l.amount
						log.action_taken = "None"
						log.investigation_notes = f"Deposit of {l.amount:,.2f} UGX remained unallocated for {hrs:.1f} hours (> {threshold_hours}h SLA). Description: {l.transaction_description}"
						log.status = "Investigating"
						log.insert(ignore_permissions=True)

		self.recompute_totals()
		self.save(ignore_permissions=True)
		return {"escalated_count": escalations}

	@frappe.whitelist()
	def create_subscriptions(self):
		"""Converts all matched lines into Asset Subscriptions (Codeunit 51404503 PostSubscriptions)."""
		created = 0
		for l in self.lines:
			if l.status == "Matched" and not l.subscription_ref:
				sub = frappe.new_doc("Asset Subscription")
				sub.investor = l.matched_investor
				sub.fund = l.fund or "SBG-MMF"
				sub.subscription_date = self.import_date
				sub.value_date = l.value_date
				sub.gross_amount = l.amount
				sub.payment_method = "Bank Transfer / BOL"
				sub.bank_reference = f"{self.name}-{l.line_no}"
				sub.bol_line_ref = f"{self.name}-{l.line_no}"
				sub.remarks = f"Auto-created from BOL statement line {l.line_no}: {l.transaction_description}"
				sub.insert(ignore_permissions=True)

				l.subscription_ref = sub.name
				l.status = "Subscription Created"
				created += 1

		self.recompute_totals()
		if all(l.status == "Subscription Created" for l in self.lines if l.status != "Exception"):
			self.status = "Processed"
		self.save(ignore_permissions=True)
		return {"created_subscriptions": created}
