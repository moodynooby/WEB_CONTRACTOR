"""Visualization components using Plotly for Web Contractor."""

from typing import Any, Dict

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def get_plotly_theme() -> Dict[str, Any]:
    """Get standard Plotly theme configuration."""
    return {
        "template": "plotly_white",
        "font": {"family": "sans-serif", "size": 12},
        "margin": {"l": 40, "r": 20, "t": 40, "b": 40},
    }


def plot_lead_funnel(leads_df: pd.DataFrame) -> go.Figure:
    """Create a lead funnel visualization showing conversion through stages.

    Args:
        leads_df: DataFrame with leads data including 'status' column.

    Returns:
        Plotly Figure object.
    """
    status_counts = leads_df["status"].value_counts()

    stages = {
        "pending_audit": "Discovered",
        "qualified": "Qualified",
        "unqualified": "Unqualified",
        "sent": "Emailed",
    }

    funnel_data = []
    for status, label in stages.items():
        count = status_counts.get(status, 0)
        funnel_data.append({"Stage": label, "Count": count})

    fig = go.Figure(
        go.Funnel(
            y=[d["Stage"] for d in funnel_data],
            x=[d["Count"] for d in funnel_data],
            textposition="inside",
            textinfo="value+percent initial",
            marker={"color": ["#636EFA", "#00CC96", "#EF553B", "#AB63FA"]},
            connector={"line": {"color": "#b2b2b2", "dash": "dot", "width": 2}},
        )
    )

    fig.update_layout(
        title="Lead Conversion Funnel",
        showlegend=False,
        height=400,
        **get_plotly_theme(),
    )

    return fig


def plot_lead_status_pie(leads_df: pd.DataFrame) -> go.Figure:
    """Create a donut chart for lead status distribution.

    Args:
        leads_df: DataFrame with leads data including 'status' column.

    Returns:
        Plotly Figure object.
    """
    status_counts = leads_df["status"].value_counts()

    fig = go.Figure(
        data=[
            go.Pie(
                labels=status_counts.index,
                values=status_counts.values,
                hole=0.4,
                marker_colors=["#636EFA", "#00CC96", "#EF553B", "#AB63FA", "#FFA15A"],
            )
        ]
    )

    fig.update_layout(
        title="Lead Status Distribution",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
        height=350,
        **get_plotly_theme(),
    )

    fig.update_traces(textposition="inside", textinfo="value+percent")

    return fig


def plot_lead_timeline(leads_df: pd.DataFrame, freq: str = "D") -> go.Figure:
    """Create a time series chart showing leads created over time.

    Args:
        leads_df: DataFrame with leads data including 'created_at' column.
        freq: Frequency for aggregation ('D' for daily, 'W' for weekly, 'M' for monthly).

    Returns:
        Plotly Figure object.
    """
    leads_df = leads_df.copy()
    leads_df["created_at"] = pd.to_datetime(leads_df["created_at"])
    leads_df["date"] = leads_df["created_at"].dt.to_period(freq).astype(str)

    daily_counts = leads_df.groupby("date").size().reset_index(name="leads")  # ty: ignore[no-matching-overload]

    fig = px.line(
        daily_counts, x="date", y="leads", markers=True, title="Leads Created Over Time"
    )

    fig.update_traces(line=dict(color="#636EFA", width=3), marker=dict(size=8))
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Number of Leads",
        height=350,
        **get_plotly_theme(),
    )

    return fig


def plot_audit_score_distribution(leads_df: pd.DataFrame) -> go.Figure:
    """Create a histogram of audit scores.

    Args:
        leads_df: DataFrame with leads data including 'audit_score' column.

    Returns:
        Plotly Figure object.
    """
    audit_scores = leads_df["audit_score"].dropna()

    if len(audit_scores) == 0:
        fig = go.Figure()
        fig.update_layout(
            title="Audit Score Distribution",
            annotations=[{"text": "No audit data available", "showarrow": False}],
        )
        return fig

    fig = px.histogram(
        audit_scores,
        nbins=20,
        title="Audit Score Distribution",
        labels={"value": "Audit Score", "count": "Number of Leads"},
    )

    fig.update_traces(marker_color="#00CC96")
    fig.update_layout(height=350, showlegend=False, **get_plotly_theme())

    return fig


def plot_platform_distribution(leads_df: pd.DataFrame) -> go.Figure:
    """Create a bar chart for platform distribution.

    Args:
        leads_df: DataFrame with leads data including 'platform_detected' column.

    Returns:
        Plotly Figure object.
    """
    if "platform_detected" not in leads_df.columns:
        return go.Figure()

    platform_counts = leads_df["platform_detected"].value_counts().head(10)

    fig = px.bar(
        x=platform_counts.values,
        y=platform_counts.index,
        orientation="h",
        title="Top Website Platforms Detected",
        labels={"x": "Count", "y": "Platform"},
    )

    fig.update_traces(marker_color="#AB63FA")
    fig.update_layout(height=350, showlegend=False, **get_plotly_theme())

    return fig


def plot_email_campaign_funnel(campaigns_df: pd.DataFrame) -> go.Figure:
    """Create email campaign funnel (sent -> opened -> clicked -> replied).

    Args:
        campaigns_df: DataFrame with email campaign data.

    Returns:
        Plotly Figure object.
    """
    stages = {
        "sent": campaigns_df.get("status").eq("sent").sum()
        if "status" in campaigns_df.columns
        else 0,
        "opened": campaigns_df["opened_at"].notna().sum()
        if "opened_at" in campaigns_df.columns
        else 0,
        "clicked": campaigns_df["clicked_at"].notna().sum()
        if "clicked_at" in campaigns_df.columns
        else 0,
        "replied": campaigns_df["replied_at"].notna().sum()
        if "replied_at" in campaigns_df.columns
        else 0,
    }

    fig = go.Figure(
        go.Funnel(
            y=list(stages.keys()),
            x=list(stages.values()),
            textposition="inside",
            textinfo="value+percent previous",
            marker={"color": ["#636EFA", "#00CC96", "#FFA15A", "#EF553B"]},
            connector={"line": {"color": "#b2b2b2", "dash": "dot", "width": 2}},
        )
    )

    fig.update_layout(
        title="Email Campaign Performance Funnel",
        showlegend=False,
        height=400,
        **get_plotly_theme(),
    )

    return fig


def plot_email_metrics_over_time(campaigns_df: pd.DataFrame) -> go.Figure:
    """Create time series chart for email metrics over time.

    Args:
        campaigns_df: DataFrame with email campaign data.

    Returns:
        Plotly Figure object.
    """
    if "sent_at" not in campaigns_df.columns:
        return go.Figure()

    campaigns_df = campaigns_df.copy()
    campaigns_df["sent_at"] = pd.to_datetime(campaigns_df["sent_at"], errors="coerce")
    campaigns_df = campaigns_df.dropna(subset=["sent_at"])

    if campaigns_df.empty:
        fig = go.Figure()
        fig.update_layout(
            title="Email Metrics Over Time",
            annotations=[{"text": "No sent email data available", "showarrow": False}],
        )
        return fig

    campaigns_df["date"] = campaigns_df["sent_at"].dt.to_period("D").astype(str)

    daily_stats = (
        campaigns_df.groupby("date")
        .agg(
            {
                "id": "count",
                "opened_at": lambda x: x.notna().sum(),
                "clicked_at": lambda x: x.notna().sum(),
                "replied_at": lambda x: x.notna().sum(),
            }
        )
        .reset_index()
    )
    daily_stats.columns = ["date", "sent", "opened", "clicked", "replied"]

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=daily_stats["date"],
            y=daily_stats["sent"],
            name="Sent",
            marker_color="#636EFA",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=daily_stats["date"],
            y=daily_stats["opened"],
            name="Opened",
            line=dict(color="#00CC96", width=2),
            mode="lines+markers",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=daily_stats["date"],
            y=daily_stats["clicked"],
            name="Clicked",
            line=dict(color="#FFA15A", width=2),
            mode="lines+markers",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=daily_stats["date"],
            y=daily_stats["replied"],
            name="Replied",
            line=dict(color="#EF553B", width=2),
            mode="lines+markers",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title="Email Campaign Performance Over Time",
        height=400,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        **get_plotly_theme(),
    )
    fig.update_yaxes(title_text="Emails Sent", secondary_y=False)
    fig.update_yaxes(title_text="Engagement Count", secondary_y=True)

    return fig


def plot_query_performance_trend(perf_df: pd.DataFrame) -> go.Figure:
    """Create time series chart for query performance.

    Args:
        perf_df: DataFrame with query performance data.

    Returns:
        Plotly Figure object.
    """
    if "last_executed_at" not in perf_df.columns:
        return go.Figure()

    perf_df = perf_df.copy()
    perf_df["last_executed_at"] = pd.to_datetime(
        perf_df["last_executed_at"], errors="coerce"
    )
    perf_df = perf_df.dropna(subset=["last_executed_at"])

    if perf_df.empty:
        fig = go.Figure()
        fig.update_layout(
            title="Query Execution Trend",
            annotations=[{"text": "No execution data available", "showarrow": False}],
        )
        return fig

    perf_df["date"] = perf_df["last_executed_at"].dt.to_period("D").astype(str)

    daily_stats = (
        perf_df.groupby("date")
        .agg(
            {
                "total_executions": "sum",
                "total_leads_found": "sum",
                "total_leads_saved": "sum",
            }
        )
        .reset_index()
    )

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=daily_stats["date"],
            y=daily_stats["total_executions"],
            name="Executions",
            line=dict(color="#636EFA", width=2),
            mode="lines+markers",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=daily_stats["date"],
            y=daily_stats["total_leads_found"],
            name="Leads Found",
            line=dict(color="#00CC96", width=2),
            mode="lines+markers",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=daily_stats["date"],
            y=daily_stats["total_leads_saved"],
            name="Leads Saved",
            line=dict(color="#AB63FA", width=2),
            mode="lines+markers",
        )
    )

    fig.update_layout(
        title="Query Performance Over Time",
        xaxis_title="Date",
        yaxis_title="Count",
        height=350,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        **get_plotly_theme(),
    )

    return fig


def plot_query_success_rate(perf_df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """Create horizontal bar chart for query success rates.

    Args:
        perf_df: DataFrame with query performance data.
        top_n: Number of top queries to show.

    Returns:
        Plotly Figure object.
    """
    perf_df = perf_df.copy()
    perf_df["success_rate"] = (
        perf_df["total_leads_saved"] / perf_df["total_executions"].clip(lower=1) * 100
    ).round(1)

    top_queries = perf_df.nlargest(top_n, "total_leads_saved")

    fig = px.bar(
        top_queries,
        x="total_leads_saved",
        y="query_pattern",
        orientation="h",
        title=f"Top {top_n} Queries by Leads Saved",
        labels={"total_leads_saved": "Leads Saved", "query_pattern": "Query Pattern"},
        color="success_rate",
        color_continuous_scale="Viridis",
    )

    fig.update_layout(
        height=400,
        showlegend=False,
        yaxis={"categoryorder": "total descending"},
        **get_plotly_theme(),
    )

    return fig


def plot_active_vs_inactive(perf_df: pd.DataFrame) -> go.Figure:
    """Create pie chart for active vs inactive queries.

    Args:
        perf_df: DataFrame with query performance data.

    Returns:
        Plotly Figure object.
    """
    active_count = perf_df["is_active"].sum()
    inactive_count = len(perf_df) - active_count

    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Active", "Inactive"],
                values=[active_count, inactive_count],
                hole=0.4,
                marker_colors=["#00CC96", "#EF553B"],
            )
        ]
    )

    fig.update_layout(
        title="Active vs Inactive Queries",
        showlegend=True,
        height=300,
        **get_plotly_theme(),
    )

    fig.update_traces(textposition="inside", textinfo="value+percent")

    return fig


def plot_bucket_performance(leads_df: pd.DataFrame) -> go.Figure:
    """Create grouped bar chart for bucket performance.

    Args:
        leads_df: DataFrame with leads data including 'bucket_id' and 'status'.

    Returns:
        Plotly Figure object.
    """
    if "bucket_id" not in leads_df.columns:
        return go.Figure()

    bucket_stats = (
        leads_df.groupby(["bucket_id", "status"]).size().unstack(fill_value=0)
    )

    fig = go.Figure()

    colors = ["#636EFA", "#00CC96", "#EF553B", "#AB63FA"]
    for i, col in enumerate(bucket_stats.columns):
        fig.add_trace(
            go.Bar(
                name=col,
                x=bucket_stats.index,
                y=bucket_stats[col],
                marker_color=colors[i % len(colors)],
            )
        )

    fig.update_layout(
        title="Lead Status by Bucket",
        xaxis_title="Bucket",
        yaxis_title="Number of Leads",
        barmode="group",
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        **get_plotly_theme(),
    )

    return fig


def plot_location_distribution(leads_df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """Create horizontal bar chart for lead distribution by location.

    Args:
        leads_df: DataFrame with leads data including 'location' column.
        top_n: Number of top locations to show.

    Returns:
        Plotly Figure object.
    """
    location_counts = leads_df["location"].value_counts().head(top_n)

    fig = px.bar(
        x=location_counts.values,
        y=location_counts.index,
        orientation="h",
        title=f"Top {top_n} Locations",
        labels={"x": "Number of Leads", "y": "Location"},
    )

    fig.update_traces(marker_color="#FFA15A")
    fig.update_layout(
        height=350,
        showlegend=False,
        yaxis={"categoryorder": "total descending"},
        **get_plotly_theme(),
    )

    return fig


def plot_top_performing_queries(perf_df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """Create a table-style visualization of top performing queries.

    Args:
        perf_df: DataFrame with query performance data.
        top_n: Number of top queries to show.

    Returns:
        Plotly Figure object.
    """
    top_queries = perf_df.nlargest(top_n, "total_leads_saved")[
        [
            "query_pattern",
            "city",
            "total_executions",
            "total_leads_saved",
            "success_rate",
        ]
    ].copy()

    fig = go.Figure(
        data=[
            go.Table(
                header=dict(
                    values=[
                        "Query Pattern",
                        "City",
                        "Executions",
                        "Leads Saved",
                        "Success Rate %",
                    ],
                    fill_color="#636EFA",
                    font=dict(color="white", size=12),
                    align="left",
                    height=35,
                ),
                cells=dict(
                    values=[
                        top_queries["query_pattern"],
                        top_queries["city"],
                        top_queries["total_executions"],
                        top_queries["total_leads_saved"],
                        top_queries["success_rate"].round(1),
                    ],
                    fill_color=[["#f5f5f5", "white"] * len(top_queries)],
                    align="left",
                    height=30,
                ),
            )
        ]
    )

    fig.update_layout(
        title=f"Top {top_n} Performing Queries",
        height=max(400, len(top_queries) * 35 + 80),
        margin=dict(l=10, r=10, t=40, b=10),
    )

    return fig


def plot_campaign_summary(campaigns_df: pd.DataFrame) -> go.Figure:
    """Create a summary gauge chart for campaign metrics.

    Args:
        campaigns_df: DataFrame with email campaign data.

    Returns:
        Plotly Figure object.
    """
    sent = (
        campaigns_df["status"].eq("sent").sum()
        if "status" in campaigns_df.columns
        else 0
    )
    opened = (
        campaigns_df["opened_at"].notna().sum()
        if "opened_at" in campaigns_df.columns
        else 0
    )
    clicked = (
        campaigns_df["clicked_at"].notna().sum()
        if "clicked_at" in campaigns_df.columns
        else 0
    )
    replied = (
        campaigns_df["replied_at"].notna().sum()
        if "replied_at" in campaigns_df.columns
        else 0
    )

    open_rate = (opened / sent * 100) if sent > 0 else 0
    click_rate = (clicked / sent * 100) if sent > 0 else 0
    reply_rate = (replied / sent * 100) if sent > 0 else 0

    fig = make_subplots(
        rows=1,
        cols=3,
        specs=[[{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}]],
        subplot_titles=["Open Rate", "Click Rate", "Reply Rate"],
    )

    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=open_rate,
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#00CC96"},
                "steps": [
                    {"range": [0, 20], "color": "#EF553B"},
                    {"range": [20, 40], "color": "#FFA15A"},
                    {"range": [40, 100], "color": "#00CC96"},
                ],
            },
            number={"suffix": "%"},
            title={"text": "Open Rate"},
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=click_rate,
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#636EFA"},
                "steps": [
                    {"range": [0, 5], "color": "#EF553B"},
                    {"range": [5, 15], "color": "#FFA15A"},
                    {"range": [15, 100], "color": "#636EFA"},
                ],
            },
            number={"suffix": "%"},
            title={"text": "Click Rate"},
        ),
        row=1,
        col=2,
    )

    fig.add_trace(
        go.Indicator(
            mode="gauge+number",
            value=reply_rate,
            gauge={
                "axis": {"range": [0, 50]},
                "bar": {"color": "#AB63FA"},
                "steps": [
                    {"range": [0, 5], "color": "#EF553B"},
                    {"range": [5, 15], "color": "#FFA15A"},
                    {"range": [15, 50], "color": "#AB63FA"},
                ],
            },
            number={"suffix": "%"},
            title={"text": "Reply Rate"},
        ),
        row=1,
        col=3,
    )

    fig.update_layout(
        height=250,
        showlegend=False,
        margin=dict(l=20, r=20, t=50, b=20),
    )

    return fig
