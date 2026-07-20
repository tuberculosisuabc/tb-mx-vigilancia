import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from db import get_lineage_dist
from utils import render_topnav, render_footer, render_sample_size

st.set_page_config(
    page_title="Linajes · SVG-TB-MX",
    page_icon="🫁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_topnav("Linajes")

# ── Header ────────────────────────────────────────────────────────────
st.markdown("""
    <h1>Distribución de Linajes</h1>
    <p style='color:#4a6278;font-size:1.05rem;line-height:1.7'>
        Filogenia y distribución geográfica de linajes de <i>M. tuberculosis</i> en México.
    </p>
""", unsafe_allow_html=True)

render_sample_size()

lineage_colors = {
    "lineage1": "#A327F5",
    "lineage2": "#f59e0b",
    "lineage3": "#22c55e",
    "lineage4": "#2D6A4F",
    "lineage5": "#a78bfa",
    "lineage6": "#f87171",
    "La1":      "#F54927",
    "La2":      "#e879f9",
}

# ── Main distribution ─────────────────────────────────────────────────
st.markdown("<div class='section-header'>Distribución Global</div>", unsafe_allow_html=True)

lin_data = get_lineage_dist()
df_lin = pd.DataFrame(lin_data)
df_lin["lineage"] = df_lin["lineage"].apply(
    lambda x: x.split(";")[0] if isinstance(x, str) and ";" in x else x
)
df_lin = df_lin.groupby("lineage", as_index=False).agg({"count": "sum"})

if "description" not in df_lin.columns:
    df_lin["description"] = df_lin["lineage"]
if "sub_lineages" not in df_lin.columns:
    df_lin["sub_lineages"] = "N/A"

col1, col2 = st.columns(2)

with col1:
    fig_donut = px.pie(
        df_lin, values="count", names="lineage",
        color="lineage", color_discrete_map=lineage_colors,
        hole=0.55,
        custom_data=["description"],
    )
    fig_donut.update_traces(
        textposition="outside",
        textfont_size=11,
        hovertemplate="<b>%{label}</b><br>%{customdata[0]}<br>Muestras: %{value}<br>%{percent}<extra></extra>",
        marker=dict(line=dict(color="#F4F1EA", width=2)),
    )
    fig_donut.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#3D5A4D", family="Poppins"),
        legend=dict(orientation="v", bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        margin=dict(t=30, b=30, l=0, r=0),
        height=500,
        annotations=[dict(
            text=f"<b>{df_lin['count'].sum()}</b><br>genomas",
            x=0.5, y=0.5, font_size=13, font_color="#1B3A2D", showarrow=False,
        )],
    )
    st.plotly_chart(fig_donut, use_container_width=True)

with col2:
    fig_bar = go.Figure(go.Bar(
        y=df_lin["lineage"],
        x=df_lin["count"],
        orientation="h",
        marker_color=[lineage_colors.get(l, "#64748b") for l in df_lin["lineage"]],
        text=df_lin["count"],
        textposition="outside",
        textfont=dict(color="#3D5A4D", size=11),
        customdata=df_lin[["description", "sub_lineages"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>%{customdata[0]}<br>"
            "Muestras: %{x}<br>Sub-linajes: %{customdata[1]}<extra></extra>"
        ),
    ))
    fig_bar.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#3D5A4D", family="Poppins"),
        xaxis=dict(showgrid=True, gridcolor="#D5D0C4", color="#4a6278"),
        yaxis=dict(showgrid=False, color="#3D5A4D", autorange="reversed"),
        margin=dict(t=10, b=10, l=10, r=60),
        height=320,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

# ── Detail table ──────────────────────────────────────────────────────
st.markdown("<div class='section-header'>Detalle de Linajes</div>", unsafe_allow_html=True)

df_display = df_lin[["lineage", "description", "count", "sub_lineages"]].copy()
df_display.columns = ["Linaje", "Descripción", "Muestras", "Sub-linajes observados"]

st.dataframe(
    df_display,
    use_container_width=True, hide_index=True,
    column_config={
        "Muestras": st.column_config.ProgressColumn(
            "Muestras", min_value=0, max_value=int(df_lin["count"].max())
        ),
    }
)

render_footer()
