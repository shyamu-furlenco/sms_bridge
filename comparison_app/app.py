import streamlit as st
import pandas as pd

from filters import (
    CITY_MAP,
    TENURE_BUCKET_OPTIONS,
    PLAN_TYPE_OPTIONS,
    NEW_RETURNING_OPTIONS,
    VERTICAL_OPTIONS,
    get_month_options,
    month_to_date_range,
)
from metrics import METRIC_META, METRIC_KEYS, compute_delta, format_value, format_delta_label
from db import run_query, scalar
from charts import build_grouped_bar
from queries import (
    build_mrr_query,
    build_active_subs_query,
    build_churn_query,
    build_revenue_billed_query,
)

st.set_page_config(
    page_title="Furlenco MoM Comparison",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .metric-card {
        background: #1e1e2e;
        border-radius: 12px;
        padding: 20px 24px;
        border: 1px solid rgba(255,255,255,0.08);
    }
    .metric-label { font-size: 13px; color: #9ca3af; font-weight: 500; margin-bottom: 4px; }
    .metric-value { font-size: 28px; font-weight: 700; color: #f9fafb; margin-bottom: 6px; }
    .metric-m1 { font-size: 12px; color: #6b7280; }
    .delta-up { color: #22c55e; font-size: 14px; font-weight: 600; }
    .delta-down { color: #ef4444; font-size: 14px; font-weight: 600; }
    .delta-flat { color: #9ca3af; font-size: 14px; font-weight: 600; }
    .filter-section {
        background: rgba(255,255,255,0.03);
        border-radius: 10px;
        padding: 16px 20px;
        border: 1px solid rgba(255,255,255,0.06);
        margin-bottom: 20px;
    }
    div[data-testid="stHorizontalBlock"] > div { gap: 12px; }
</style>
""", unsafe_allow_html=True)


def render_metric_card(key: str, delta: dict):
    meta = METRIC_META[key]
    fmt = meta["format"]
    invert = meta["invert_delta"]

    m2_str = format_value(delta["m2"], fmt)
    m1_str = format_value(delta["m1"], fmt)
    delta_str = format_delta_label(delta, fmt)

    direction = delta["direction"]
    if invert:
        css_class = "delta-down" if direction == "up" else ("delta-up" if direction == "down" else "delta-flat")
    else:
        css_class = "delta-up" if direction == "up" else ("delta-down" if direction == "down" else "delta-flat")

    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{meta['label']}</div>
        <div class="metric-value">{m2_str}</div>
        <div class="{css_class}">{delta_str}</div>
        <div class="metric-m1">vs {m1_str} prev month</div>
    </div>
    """, unsafe_allow_html=True)


def collect_filters():
    months = get_month_options(24)
    city_names = ["All Cities"] + list(CITY_MAP.values())

    with st.container():
        st.markdown('<div class="filter-section">', unsafe_allow_html=True)

        row1 = st.columns([1.2, 1.2, 2, 2])
        with row1[0]:
            m1 = st.selectbox("Month 1 (Base)", months, index=2, key="m1")
        with row1[1]:
            m2 = st.selectbox("Month 2 (Compare)", months, index=1, key="m2")
        with row1[2]:
            selected_cities = st.multiselect(
                "Cities",
                list(CITY_MAP.values()),
                default=[],
                placeholder="All Cities",
                key="cities",
            )
        with row1[3]:
            selected_verticals_raw = st.multiselect(
                "Product Vertical",
                [v for v in VERTICAL_OPTIONS if v != "All"],
                default=[],
                placeholder="All Verticals",
                key="verticals",
            )

        row2 = st.columns([1.5, 1.5, 1.5, 1])
        with row2[0]:
            new_returning = st.selectbox("Customer Type", NEW_RETURNING_OPTIONS, key="nr")
        with row2[1]:
            tenure_label = st.selectbox("Tenure Bucket", list(TENURE_BUCKET_OPTIONS.keys()), key="tenure")
        with row2[2]:
            plan_label = st.selectbox("Plan Type", list(PLAN_TYPE_OPTIONS.keys()), key="plan")
        with row2[3]:
            st.markdown("<br>", unsafe_allow_html=True)
            run_clicked = st.button("▶ Run Comparison", type="primary", use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

    city_ids = [k for k, v in CITY_MAP.items() if v in selected_cities]
    verticals = selected_verticals_raw or []
    tenure_range = TENURE_BUCKET_OPTIONS[tenure_label]
    plan_months = PLAN_TYPE_OPTIONS[plan_label]

    return {
        "m1": m1,
        "m2": m2,
        "city_ids": city_ids,
        "verticals": verticals,
        "new_returning": new_returning,
        "tenure_range": tenure_range,
        "plan_months": plan_months,
        "run": run_clicked,
    }


def fetch_all_metrics(filters: dict, month_start: str, month_end_exclusive: str, month_end_date: str):
    kw = {
        "city_ids": filters["city_ids"],
        "verticals": filters["verticals"],
        "new_returning": filters["new_returning"],
        "tenure_range": filters["tenure_range"],
        "plan_months": filters["plan_months"],
    }

    queries = {
        "mrr": build_mrr_query(month_start, month_end_exclusive, **kw),
        "active_subscriptions": build_active_subs_query(month_end_date, month_start=month_start, **kw),
        "churned_customers": build_churn_query(month_start, month_end_exclusive, **kw),
        "revenue_billed": build_revenue_billed_query(month_start, month_end_exclusive, **kw),
    }

    results = {}
    errors = []
    for key, (sql, params) in queries.items():
        try:
            df = run_query(sql, tuple(params))
            results[key] = scalar(df)
        except Exception as e:
            errors.append(f"{METRIC_META[key]['label']}: {e}")
            results[key] = None

    return results, errors


def render_results(f: dict, m1_results: dict, m2_results: dict):
    m1_label = f["m1"]
    m2_label = f["m2"]

    deltas = {k: compute_delta(m1_results[k], m2_results[k]) for k in METRIC_KEYS}

    st.markdown("#### Key Metrics")
    cols = st.columns(4)
    for i, key in enumerate(METRIC_KEYS):
        with cols[i]:
            render_metric_card(key, deltas[key])

    st.markdown("#### Month-over-Month Comparison")
    chart_data = {k: {"m1": deltas[k]["m1"], "m2": deltas[k]["m2"]} for k in METRIC_KEYS}
    fig = build_grouped_bar(chart_data, m1_label, m2_label)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Summary Table")
    rows = []
    for key in METRIC_KEYS:
        meta = METRIC_META[key]
        d = deltas[key]
        fmt = meta["format"]
        rows.append({
            "Metric": meta["label"],
            f"{m1_label}": format_value(d["m1"], fmt),
            f"{m2_label}": format_value(d["m2"], fmt),
            "Abs Diff": format_delta_label(d, fmt).split(" (")[0],
            "% Change": f"{d['pct_change']:+.1f}%" if d["pct_change"] is not None else "N/A",
        })

    summary_df = pd.DataFrame(rows)
    st.dataframe(summary_df, hide_index=True, use_container_width=True)


def main():
    st.title("📊 Month-over-Month Business Comparison")
    st.caption("Compare MRR, Active Subscriptions, Churn, and Revenue Billed across any two months.")

    filters = collect_filters()

    if filters["m1"] == filters["m2"]:
        st.warning("Please select two different months.")
        return

    if "last_results" not in st.session_state:
        st.session_state.last_results = None

    if filters["run"]:
        m1_start, m1_end_ex, m1_end_inc = month_to_date_range(filters["m1"])
        m2_start, m2_end_ex, m2_end_inc = month_to_date_range(filters["m2"])

        with st.spinner("Fetching data..."):
            m1_results, m1_errors = fetch_all_metrics(filters, m1_start, m1_end_ex, m1_end_inc)
            m2_results, m2_errors = fetch_all_metrics(filters, m2_start, m2_end_ex, m2_end_inc)

        all_errors = m1_errors + m2_errors
        if all_errors:
            for err in all_errors:
                st.error(f"Query error — {err}")

        st.session_state.last_results = {
            "filters": filters,
            "m1_results": m1_results,
            "m2_results": m2_results,
        }

    if st.session_state.last_results:
        r = st.session_state.last_results
        render_results(r["filters"], r["m1_results"], r["m2_results"])
    else:
        st.info("Configure filters above and click **▶ Run Comparison** to load data.")


if __name__ == "__main__":
    main()
