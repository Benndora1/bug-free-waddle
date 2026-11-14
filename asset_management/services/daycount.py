import calendar
from datetime import date, timedelta
from decimal import Decimal


def _days_in_year(year: int) -> int:
	return 366 if calendar.isleap(year) else 365


def year_fraction(
	start_date: date,
	end_date: date,
	convention: str = "ACT/365F",
) -> Decimal:
	"""Pure day-count fraction calculator supporting ACT/365F, ACT/360, ACT/ACT, and 30/360."""
	if end_date <= start_date:
		return Decimal("0")

	conv = (convention or "ACT/365F").strip().upper()
	actual_days = Decimal((end_date - start_date).days)

	if conv in ("ACT/365F", "ACT/365", "ACTUAL/365", "ACTUAL/365F"):
		return actual_days / Decimal("365")

	if conv in ("ACT/360", "ACTUAL/360"):
		return actual_days / Decimal("360")

	if conv in ("ACT/ACT", "ACTUAL/ACTUAL", "ACT/ACT ISDA"):
		if start_date.year == end_date.year:
			return actual_days / Decimal(_days_in_year(start_date.year))

		# Split across calendar years (ISDA Actual/Actual)
		fraction = Decimal("0")
		cur = start_date
		while cur.year < end_date.year:
			next_year_start = date(cur.year + 1, 1, 1)
			days_in_slice = Decimal((next_year_start - cur).days)
			fraction += days_in_slice / Decimal(_days_in_year(cur.year))
			cur = next_year_start
		if cur < end_date:
			days_in_slice = Decimal((end_date - cur).days)
			fraction += days_in_slice / Decimal(_days_in_year(cur.year))
		return fraction

	if conv in ("30/360", "30U/360", "360/360"):
		d1 = min(start_date.day, 30)
		d2 = min(end_date.day, 30) if d1 == 30 else end_date.day
		days_360 = (
			360 * (end_date.year - start_date.year) + 30 * (end_date.month - start_date.month) + (d2 - d1)
		)
		return Decimal(max(days_360, 0)) / Decimal("360")

	raise ValueError(f"Unsupported day-count convention: {convention}")


def previous_business_day(
	target_date: date,
	holidays: set[date] | None = None,
) -> date:
	"""Returns the immediately preceding business day (skipping Saturday/Sunday and optional holidays)."""
	holiday_set = holidays or set()
	candidate = target_date - timedelta(days=1)
	while candidate.weekday() >= 5 or candidate in holiday_set:
		candidate -= timedelta(days=1)
	return candidate
