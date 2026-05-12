import os
import pandas as pd
import streamlit as st


@st.cache_resource
def get_connection():
    import databricks.sql as sql
    host = os.environ["DATABRICKS_HOST"].replace("https://", "")
    return sql.connect(
        server_hostname=host,
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ.get("DATABRICKS_TOKEN", ""),
    )


@st.cache_data(ttl=600, show_spinner=False)
def run_query(query: str, _params: tuple = ()) -> pd.DataFrame:
    """Run a SQL query and return results as a DataFrame.
    Uses _params (tuple) so Streamlit can hash it for cache keying.
    The query itself should have %s placeholders in order."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(query, list(_params) if _params else None)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return pd.DataFrame(rows, columns=cols)


def scalar(df: pd.DataFrame, col: str = None):
    """Extract first scalar value from a single-cell DataFrame."""
    if df is None or df.empty:
        return 0
    col = col or df.columns[0]
    val = df[col].iloc[0]
    return 0 if val is None else val
