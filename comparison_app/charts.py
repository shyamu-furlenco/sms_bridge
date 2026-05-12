import plotly.graph_objects as go
from plotly.subplots import make_subplots
from metrics import METRIC_META, format_value

M1_COLOR = "#4C6EF5"
M2_COLOR = "#F76707"


def build_grouped_bar(results: dict, m1_label: str, m2_label: str) -> go.Figure:
    """
    results: {metric_key: {"m1": val, "m2": val}} for each of the 4 metrics
    One subplot per metric to avoid mixed-unit y-axis distortion.
    """
    metric_keys = list(results.keys())
    titles = [METRIC_META[k]["label"] for k in metric_keys]

    fig = make_subplots(
        rows=1,
        cols=len(metric_keys),
        subplot_titles=titles,
        horizontal_spacing=0.08,
    )

    for idx, key in enumerate(metric_keys, start=1):
        meta = METRIC_META[key]
        v1 = results[key]["m1"]
        v2 = results[key]["m2"]
        fmt = meta["format"]

        fig.add_trace(
            go.Bar(
                name=m1_label,
                x=[m1_label],
                y=[v1],
                marker_color=M1_COLOR,
                text=[format_value(v1, fmt)],
                textposition="outside",
                showlegend=(idx == 1),
            ),
            row=1,
            col=idx,
        )
        fig.add_trace(
            go.Bar(
                name=m2_label,
                x=[m2_label],
                y=[v2],
                marker_color=M2_COLOR,
                text=[format_value(v2, fmt)],
                textposition="outside",
                showlegend=(idx == 1),
            ),
            row=1,
            col=idx,
        )

    fig.update_layout(
        barmode="group",
        height=360,
        margin=dict(t=50, b=20, l=20, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(showticklabels=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)", zeroline=False)

    return fig
