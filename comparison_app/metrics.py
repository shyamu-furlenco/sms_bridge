METRIC_META = {
    "mrr": {
        "label": "MRR",
        "format": "currency",
        "invert_delta": False,
        "help": "Monthly Recurring Revenue (pre-tax) from recognized revenue",
    },
    "active_subscriptions": {
        "label": "Active Subscriptions",
        "format": "count",
        "invert_delta": False,
        "help": "Unique customers with at least one active item at month end",
    },
    "churned_customers": {
        "label": "Churn",
        "format": "count",
        "invert_delta": True,
        "help": "Unique customers whose items were picked up during the month",
    },
    "revenue_billed": {
        "label": "Revenue Billed",
        "format": "currency",
        "invert_delta": False,
        "help": "Pre-tax revenue from invoiced billing cycles created in the month",
    },
}

METRIC_KEYS = list(METRIC_META.keys())


def compute_delta(m1_val, m2_val) -> dict:
    m1 = float(m1_val or 0)
    m2 = float(m2_val or 0)
    abs_diff = m2 - m1
    pct_change = ((m2 - m1) / m1 * 100) if m1 != 0 else None
    return {
        "m1": m1,
        "m2": m2,
        "abs_diff": abs_diff,
        "pct_change": pct_change,
        "direction": "up" if abs_diff > 0 else ("down" if abs_diff < 0 else "flat"),
    }


def fmt_currency(value) -> str:
    if value is None:
        return "N/A"
    v = float(value)
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e7:
        return f"{sign}Rs {v/1e7:.2f}Cr"
    elif v >= 1e5:
        return f"{sign}Rs {v/1e5:.2f}L"
    elif v >= 1e3:
        return f"{sign}Rs {v/1e3:.1f}K"
    return f"{sign}Rs {v:,.0f}"


def fmt_count(value) -> str:
    if value is None:
        return "N/A"
    v = int(value)
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e5:
        return f"{sign}{v/1e5:.1f}L"
    elif v >= 1e3:
        return f"{sign}{v/1e3:.1f}K"
    return f"{sign}{v:,}"


def format_value(value, fmt: str) -> str:
    return fmt_currency(value) if fmt == "currency" else fmt_count(value)


def format_delta_label(delta: dict, fmt: str) -> str:
    d = delta["abs_diff"]
    pct = delta["pct_change"]
    prefix = "+" if d >= 0 else ""
    abs_str = fmt_currency(d) if fmt == "currency" else fmt_count(d)
    if not abs_str.startswith("-"):
        abs_str = f"+{abs_str}"
    if pct is not None:
        return f"{abs_str} ({pct:+.1f}%)"
    return abs_str
