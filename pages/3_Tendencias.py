import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from db import get_mdr_trend, get_lineage_by_year
from utils import render_topnav, render_footer, render_sample_size
from utils import LINEAGE_COLORS, lineage_es

st.set_page_config(
    page_title="Tendencias · SVG-TB-MX",
    page_icon="🫁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_topnav("Tendencias")

# ── Header ────────────────────────────────────────────────────────────
st.markdown("""
    <h1>Tendencias Temporales</h1>
    <p style='color:#3D5A4D;font-size:1.05rem;line-height:1.7'>
        Evolución de la TB-MDR y distribución de linajes por año (solo genomas con QC aprobado y año de colección conocido).
    </p>
""", unsafe_allow_html=True)

render_sample_size()

# ── MDR Trend ─────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>Tasa de TB-MDR por año</div>", unsafe_allow_html=True)

with st.spinner("Cargando tendencias..."):
    trend_data = get_mdr_trend()

df_trend = pd.DataFrame(trend_data)

fig = go.Figure()
fig.add_trace(go.Bar(
    x=df_trend["year"], y=df_trend["total"],
    name="Total muestras",
    marker_color="#B0C9B8",
    yaxis="y",
    hovertemplate="<b>%{x}</b><br>Total: %{y}<extra></extra>",
))
fig.add_trace(go.Bar(
    x=df_trend["year"], y=df_trend["mdr"],
    name="TB-MDR",
    marker_color="#C44B2B",
    yaxis="y",
    hovertemplate="<b>%{x}</b><br>TB-MDR: %{y}<extra></extra>",
))
fig.add_trace(go.Scatter(
    x=df_trend["year"], y=df_trend["mdr_rate"],
    name="Tasa TB-MDR (%)",
    mode="lines+markers",
    line=dict(color="#2D6A4F", width=2.5),
    marker=dict(size=7, color="#2D6A4F"),
    yaxis="y2",
    hovertemplate="<b>%{x}</b><br>Tasa TB-MDR: %{y}%<extra></extra>",
))
fig.update_layout(
    barmode="overlay",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#3D5A4D", family="Poppins"),
    xaxis=dict(showgrid=False, color="#3D5A4D", tickmode="linear", dtick=1),
    yaxis=dict(title="Número de muestras", showgrid=True, gridcolor="#D5D0C4", color="#3D5A4D"),
    yaxis2=dict(
        title="Tasa TB-MDR (%)",
        overlaying="y", side="right",
        showgrid=False, color="#2D6A4F",
        range=[0, max(df_trend["mdr_rate"].max() * 1.3, 30)],
    ),
    legend=dict(orientation="h", y=1.08, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    margin=dict(t=40, b=40, l=60, r=60),
    height=400,
    hovermode="x unified",
)
st.plotly_chart(fig, use_container_width=True)

max_year = df_trend.loc[df_trend["mdr_rate"].idxmax()]
st.info(f"Año con mayor tasa de TB-MDR: **{int(max_year['year'])}** — "
        f"{max_year['mdr_rate']}% ({int(max_year['mdr'])} de {int(max_year['total'])} muestras)")

# ── Lineage by year ───────────────────────────────────────────────────
st.markdown("<div class='section-header'>Distribución de Linajes por Año</div>", unsafe_allow_html=True)

lin_data = get_lineage_by_year()
df_lin = pd.DataFrame(lin_data)

if not df_lin.empty:
    df_lin["lineage"] = df_lin["lineage"].map(lineage_es)
    df_lin = df_lin.groupby(["year", "lineage"], as_index=False)["n"].sum()
    chart_type = st.radio(
        "Tipo de gráfica", ["Área apilada", "Barras apiladas"],
        horizontal=True, label_visibility="collapsed",
    )
    y_label = "Número de muestras"
    if chart_type == "Área apilada":
        fig2 = px.area(
            df_lin, x="year", y="n", color="lineage",
            color_discrete_map=LINEAGE_COLORS,
            labels={"n": y_label, "year": "Año", "lineage": "Linaje"},
        )
        fig2.update_traces(line=dict(width=0.5))
    else:
        fig2 = px.bar(
            df_lin, x="year", y="n", color="lineage",
            color_discrete_map=LINEAGE_COLORS,
            barmode="stack",
            labels={"n": y_label, "year": "Año", "lineage": "Linaje"},
        )
    fig2.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#3D5A4D", family="Poppins"),
        xaxis=dict(showgrid=False, color="#3D5A4D", tickmode="linear", dtick=1),
        yaxis=dict(showgrid=True, gridcolor="#D5D0C4", color="#3D5A4D", title=y_label),
        legend=dict(orientation="h", y=1.08, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        margin=dict(t=40, b=40, l=60, r=20),
        height=380,
        hovermode="x unified",
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Raw data ──────────────────────────────────────────────────────────
with st.expander("Ver datos crudos de tendencias"):
    st.dataframe(
        df_trend.rename(columns={
            "year": "Año", "total": "Total",
            "mdr": "TB-MDR", "mdr_rate": "Tasa TB-MDR (%)"
        }),
        use_container_width=True, hide_index=True,
    )

render_footer()
