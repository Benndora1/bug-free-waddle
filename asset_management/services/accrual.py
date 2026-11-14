from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from asset_management.services.daycount import year_fraction


@dataclass(frozen=True)
class FeeRule:
	fee_type: str
	basis_type: str = "GAV"
	annual_rate_pct: Decimal = Decimal("0.0")
	day_count: str = "ACT/365F"
	expense_account: str | None = None


def calculate_fee_accrual(
	basis_amount: Decimal | float | int,
	annual_rate_pct: Decimal | float | int,
	start_date: date,
	end_date: date,
	day_count: str = "ACT/365F",
) -> Decimal:
	"""Pure fee accrual calculation:

	fee_accrual = basis * (rate / 100) * year_fraction(start_date, end_date, day_count)
	Rounded to 2 decimal places (ROUND_HALF_UP).
	"""
	basis = Decimal(str(basis_amount or "0.00"))
	rate = Decimal(str(annual_rate_pct or "0.0"))
	if basis <= Decimal("0.00") or rate <= Decimal("0.0") or end_date <= start_date:
		return Decimal("0.00")

	yf = year_fraction(start_date, end_date, day_count)
	accrual = basis * (rate / Decimal("100")) * yf
	return accrual.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_fund_fee_accruals(
	rules: list[FeeRule],
	gav: Decimal | float | int,
	prior_nav: Decimal | float | int,
	start_date: date,
	end_date: date,
) -> dict[str, Decimal]:
	"""Evaluates a list of FeeRule definitions for the period (start_date, end_date].

	Each rule names its basis ('Prior NAV' or 'GAV') and day-count convention.
	Returns a dictionary mapping fee_type -> rounded Decimal accrual plus 'total'.
	"""
	gav_dec = Decimal(str(gav or "0.00"))
	prior_nav_dec = Decimal(str(prior_nav or "0.00"))

	results: dict[str, Decimal] = {}
	total = Decimal("0.00")

	for rule in rules:
		basis_norm = (rule.basis_type or "GAV").strip().upper()
		if basis_norm in ("PRIOR NAV", "PRIOR_NAV"):
			basis_val = prior_nav_dec if prior_nav_dec > Decimal("0.00") else gav_dec
		else:
			basis_val = gav_dec

		amt = calculate_fee_accrual(
			basis_amount=basis_val,
			annual_rate_pct=rule.annual_rate_pct,
			start_date=start_date,
			end_date=end_date,
			day_count=rule.day_count or "ACT/365F",
		)
		results[rule.fee_type] = results.get(rule.fee_type, Decimal("0.00")) + amt
		total += amt

	results["total"] = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	return results
