from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

CITY_MAP = {
    1: "Bengaluru",
    2: "Mumbai",
    4: "Delhi",
    5: "Gurugram",
    6: "Noida",
    7: "Hyderabad",
    8: "Chennai",
    9: "Pune",
    10: "Kolkata",
}

TENURE_BUCKET_OPTIONS = {
    "All": None,
    "0-3 months": (0, 3),
    "3-6 months": (3, 6),
    "6-12 months": (6, 12),
    "12+ months": (12, None),
}

PLAN_TYPE_OPTIONS = {
    "All": None,
    "Monthly (1m)": 1,
    "Quarterly (3m)": 3,
    "Semi-Annual (6m)": 6,
    "Annual (12m)": 12,
}

NEW_RETURNING_OPTIONS = ["All", "New", "Returning"]

VERTICAL_OPTIONS = ["All", "FURLENCO_RENTAL", "FURNITURE", "APPLIANCES", "MATTRESSES"]


def get_month_options(n: int = 18) -> list:
    today = date.today().replace(day=1)
    return [(today - relativedelta(months=i)).strftime("%Y-%m") for i in range(n)]


def month_to_date_range(yyyymm: str):
    """Returns (month_start_str, month_end_exclusive_str, month_end_inclusive_str)."""
    from datetime import datetime
    start = datetime.strptime(yyyymm, "%Y-%m").date()
    next_month = start + relativedelta(months=1)
    end_inclusive = next_month - timedelta(days=1)
    return str(start), str(next_month), str(end_inclusive)
