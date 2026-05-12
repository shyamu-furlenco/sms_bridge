"""
SQL query builders for each metric.
All filter values come from controlled dropdowns — city IDs are integers,
verticals and states are from known enums. Dates use %s parameterization.
"""


def _city_filter_furbooks(city_ids: list, alias: str) -> str:
    if not city_ids:
        return ""
    ids = ", ".join(str(c) for c in city_ids)
    return f"AND {alias}.city_id IN ({ids})"


def _vertical_filter(verticals: list, alias: str) -> str:
    if not verticals:
        return ""
    quoted = ", ".join(f"'{v}'" for v in verticals)
    return f"AND {alias}.vertical IN ({quoted})"


def _city_customers_cte(city_ids: list) -> str:
    """CTE resolving customer_identifiers for given city IDs via invoiceable_groups."""
    if not city_ids:
        return ""
    ids = ", ".join(str(c) for c in city_ids)
    return f"""city_customers AS (
    SELECT DISTINCT customer_identifier
    FROM furbooks_evolve.invoiceable_groups
    WHERE city_id IN ({ids})
),
"""


def _city_join_sms(city_ids: list) -> str:
    if not city_ids:
        return ""
    return "JOIN city_customers cc ON cc.customer_identifier = json_extract_path_text(o.user_details, 'displayId')"


def _new_returning_parts(new_returning: str, month_start: str, month_end_exclusive: str) -> tuple:
    """Returns (extra_cte, join_sql, where_condition) for new/returning segment filter."""
    if not new_returning or new_returning == "All":
        return "", "", ""

    cte = """first_activation AS (
    SELECT
        json_extract_path_text(o2.user_details, 'displayId') AS cust_id,
        MIN(i2.activation_date) AS first_act_date
    FROM order_management_systems_evolve.items i2
    JOIN order_management_systems_evolve.orders o2 ON i2.order_id = o2.id
    WHERE i2.vertical = 'FURLENCO_RENTAL'
    GROUP BY json_extract_path_text(o2.user_details, 'displayId')
),
"""
    join_sql = "JOIN first_activation fa ON fa.cust_id = json_extract_path_text(o.user_details, 'displayId')"
    if new_returning == "New":
        where_cond = f"AND fa.first_act_date >= '{month_start}' AND fa.first_act_date < '{month_end_exclusive}'"
    else:
        where_cond = f"AND fa.first_act_date < '{month_start}'"

    return cte, join_sql, where_cond


def _new_returning_parts_furbooks(new_returning: str, month_start: str, month_end_exclusive: str) -> tuple:
    """Returns (extra_cte, join_sql, where_condition) for Furbooks tables (join via customer_identifier)."""
    if not new_returning or new_returning == "All":
        return "", "", ""

    cte = """first_activation AS (
    SELECT
        json_extract_path_text(o2.user_details, 'displayId') AS cust_id,
        MIN(i2.activation_date) AS first_act_date
    FROM order_management_systems_evolve.items i2
    JOIN order_management_systems_evolve.orders o2 ON i2.order_id = o2.id
    WHERE i2.vertical = 'FURLENCO_RENTAL'
    GROUP BY json_extract_path_text(o2.user_details, 'displayId')
),
"""
    join_sql = "JOIN first_activation fa ON fa.cust_id = rr.customer_identifier"
    if new_returning == "New":
        where_cond = f"AND fa.first_act_date >= '{month_start}' AND fa.first_act_date < '{month_end_exclusive}'"
    else:
        where_cond = f"AND fa.first_act_date < '{month_start}'"

    return cte, join_sql, where_cond


def _tenure_filter(tenure_range, alias: str) -> str:
    if not tenure_range:
        return ""
    lo, hi = tenure_range
    parts = []
    if lo is not None:
        parts.append(f"{alias}.tenure_in_months >= {lo}")
    if hi is not None:
        parts.append(f"{alias}.tenure_in_months < {hi}")
    return "AND " + " AND ".join(parts) if parts else ""


def _plan_filter(plan_months, alias: str) -> str:
    if plan_months is None:
        return ""
    return f"AND {alias}.tenure_in_months = {plan_months}"


def build_mrr_query(
    month_start: str,
    month_end_exclusive: str,
    city_ids: list = None,
    verticals: list = None,
    new_returning: str = "All",
    tenure_range=None,
    plan_months=None,
) -> tuple:
    city_f = _city_filter_furbooks(city_ids, "rr")
    vert_f = _vertical_filter(verticals, "rr")
    nr_cte, nr_join, nr_where = _new_returning_parts_furbooks(new_returning, month_start, month_end_exclusive)

    sql = f"""
WITH {nr_cte}
rr_base AS (
    SELECT
        COALESCE(json_extract_path_text(rr.monetary_components, 'taxableAmount'), '0')::FLOAT AS taxable_amount
    FROM furbooks_evolve.revenue_recognitions rr
    {nr_join}
    WHERE rr.deleted_at IS NULL
      AND rr.state IN ('PROCESSED', 'FUTURE')
      AND rr.to_be_recognised_on >= %s
      AND rr.to_be_recognised_on < %s
      {nr_where}
      {city_f}
      {vert_f}
)
SELECT COALESCE(SUM(taxable_amount), 0) AS mrr FROM rr_base
"""
    return sql.strip(), (month_start, month_end_exclusive)


def build_active_subs_query(
    month_end_date: str,
    month_start: str = "",
    city_ids: list = None,
    verticals: list = None,
    new_returning: str = "All",
    tenure_range=None,
    plan_months=None,
) -> tuple:
    city_cte = _city_customers_cte(city_ids)
    city_join = _city_join_sms(city_ids)
    vert_f = _vertical_filter(verticals, "o")
    ten_f = _tenure_filter(tenure_range, "i")
    plan_f = _plan_filter(plan_months, "i")
    # For active subs new/returning, use the month containing month_end_date
    nr_cte, nr_join, nr_where = _new_returning_parts(new_returning, month_start, month_end_date)

    sql = f"""
WITH {city_cte}{nr_cte}
items_base AS (
    SELECT
        i.activation_date,
        i.pickup_date,
        json_extract_path_text(o.user_details, 'displayId') AS customer_identifier
    FROM order_management_systems_evolve.items i
    JOIN order_management_systems_evolve.orders o ON i.order_id = o.id
    {city_join}
    {nr_join}
    WHERE i.vertical = 'FURLENCO_RENTAL'
      AND i.state NOT IN ('CANCELLED', 'SWAPPED', 'PURCHASED')
      {nr_where}
      {vert_f}
      {ten_f}
      {plan_f}
)
SELECT COUNT(DISTINCT customer_identifier) AS active_subscriptions
FROM items_base
WHERE activation_date <= %s
  AND (pickup_date IS NULL OR pickup_date > %s)
"""
    return sql.strip(), (month_end_date, month_end_date)


def build_churn_query(
    month_start: str,
    month_end_exclusive: str,
    city_ids: list = None,
    verticals: list = None,
    new_returning: str = "All",
    tenure_range=None,
    plan_months=None,
) -> tuple:
    city_cte = _city_customers_cte(city_ids)
    city_join = _city_join_sms(city_ids)
    vert_f = _vertical_filter(verticals, "o")
    ten_f = _tenure_filter(tenure_range, "i")
    plan_f = _plan_filter(plan_months, "i")
    nr_cte, nr_join, nr_where = _new_returning_parts(new_returning, month_start, month_end_exclusive)

    sql = f"""
WITH {city_cte}{nr_cte}
churn_base AS (
    SELECT
        i.pickup_date,
        json_extract_path_text(o.user_details, 'displayId') AS customer_identifier
    FROM order_management_systems_evolve.items i
    JOIN order_management_systems_evolve.orders o ON i.order_id = o.id
    {city_join}
    {nr_join}
    WHERE i.vertical = 'FURLENCO_RENTAL'
      AND i.state = 'PICKED_UP'
      {nr_where}
      {vert_f}
      {ten_f}
      {plan_f}
)
SELECT COUNT(DISTINCT customer_identifier) AS churned_customers
FROM churn_base
WHERE pickup_date >= %s
  AND pickup_date < %s
"""
    return sql.strip(), (month_start, month_end_exclusive)


def build_revenue_billed_query(
    month_start: str,
    month_end_exclusive: str,
    city_ids: list = None,
    verticals: list = None,
    new_returning: str = "All",
    tenure_range=None,
    plan_months=None,
) -> tuple:
    city_f = _city_filter_furbooks(city_ids, "ic")
    vert_f = _vertical_filter(verticals, "ic")
    nr_cte, nr_join, nr_where = _new_returning_parts_furbooks(new_returning, month_start, month_end_exclusive)
    # Revenue billed uses ic.customer_identifier
    if nr_join:
        nr_join = nr_join.replace("rr.customer_identifier", "ic.customer_identifier")

    sql = f"""
WITH {nr_cte}
ic_base AS (
    SELECT
        COALESCE(json_extract_path_text(ic.monetary_components, 'taxableAmount'), '0')::FLOAT AS taxable_amount
    FROM furbooks_evolve.invoice_cycles ic
    {nr_join}
    WHERE ic.deleted_at IS NULL
      AND ic.state IN ('INVOICED', 'READY_TO_BE_INVOICED')
      AND ic.created_at >= %s
      AND ic.created_at < %s
      {nr_where}
      {city_f}
      {vert_f}
)
SELECT COALESCE(SUM(taxable_amount), 0) AS revenue_billed FROM ic_base
"""
    return sql.strip(), (month_start, month_end_exclusive)
