import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import get_lineage_by_year, get_mdr_trend
from utils import (AXIS_GRID, AXIS_PLAIN, LINEAGE_COLORS, LINK, lineage_es, page_header,
                   render_footer, section, setup_page, show_fig, style_fig)

setup_page("Tendencias")

page_header(
    "Tendencias Temporales",
    """Evolución de la TB-MDR y distribución de linajes por año (solo genomas con QC aprobado y año
    de colección conocido).""",
)

YEAR_AXIS = dict(AXIS_PLAIN, tickmode="linear", dtick=1)
Y_LABEL   = "Número de muestras"

# ── Tasa de TB-MDR por año ───────────────────────────────────────────
section("Tasa de TB-MDR por año")

with st.spinner("Cargando tendencias..."):
    df_trend = pd.DataFrame(get_mdr_trend())

fig = go.Figure()
fig.add_trace(go.Bar(
    x=df_trend["year"], y=df_trend["total"],
    name="Total muestras",
    marker_color="#B0C9B8",
    hovertemplate="<b>%{x}</b><br>Total: %{y}<extra></extra>",
))
fig.add_trace(go.Bar(
    x=df_trend["year"], y=df_trend["mdr"],
    name="TB-MDR",
    marker_color="#C44B2B",
    hovertemplate="<b>%{x}</b><br>TB-MDR: %{y}<extra></extra>",
))
fig.add_trace(go.Scatter(
    x=df_trend["year"], y=df_trend["mdr_rate"],
    name="Tasa TB-MDR (%)",
    mode="lines+markers",
    line=dict(color=LINK, width=2.5),
    marker=dict(size=7, color=LINK),
    yaxis="y2",
    hovertemplate="<b>%{x}</b><br>Tasa TB-MDR: %{y}%<extra></extra>",
))
style_fig(
    fig, height=400, margin=dict(t=40, b=40, l=60, r=60),
    legend=dict(orientation="h", y=1.08),
    barmode="overlay",
    hovermode="x unified",
    xaxis=YEAR_AXIS,
    yaxis=dict(AXIS_GRID, title=Y_LABEL),
    yaxis2=dict(title="Tasa TB-MDR (%)", overlaying="y", side="right", showgrid=False, color=LINK,
                range=[0, max(df_trend["mdr_rate"].max() * 1.3, 30)]),
)
show_fig(fig)

max_year = df_trend.loc[df_trend["mdr_rate"].idxmax()]
st.info(f"Año con mayor tasa de TB-MDR: **{int(max_year['year'])}** — "
        f"{max_year['mdr_rate']}% ({int(max_year['mdr'])} de {int(max_year['total'])} muestras)")

# ── Linajes por año ──────────────────────────────────────────────────
section("Distribución de Linajes por Año")

df_lin = pd.DataFrame(get_lineage_by_year())

if not df_lin.empty:
    df_lin["lineage"] = df_lin["lineage"].map(lineage_es)
    df_lin = df_lin.groupby(["year", "lineage"], as_index=False)["n"].sum()

    chart_type = st.radio("Tipo de gráfica", ["Área apilada", "Barras apiladas"],
                          horizontal=True, label_visibility="collapsed")
    labels = {"n": Y_LABEL, "year": "Año", "lineage": "Linaje"}
    if chart_type == "Área apilada":
        fig2 = px.area(df_lin, x="year", y="n", color="lineage",
                       color_discrete_map=LINEAGE_COLORS, labels=labels)
        fig2.update_traces(line=dict(width=0.5))
    else:
        fig2 = px.bar(df_lin, x="year", y="n", color="lineage", barmode="stack",
                      color_discrete_map=LINEAGE_COLORS, labels=labels)
    style_fig(fig2, height=380, margin=dict(t=40, b=40, l=60, r=20),
              legend=dict(orientation="h", y=1.08), hovermode="x unified",
              xaxis=YEAR_AXIS, yaxis=dict(AXIS_GRID, title=Y_LABEL))
    show_fig(fig2)

# ── Datos ────────────────────────────────────────────────────────────
with st.expander("Ver datos crudos de tendencias"):
    st.dataframe(
        df_trend.rename(columns={"year": "Año", "total": "Total",
                                 "mdr": "TB-MDR", "mdr_rate": "Tasa TB-MDR (%)"}),
        use_container_width=True, hide_index=True,
    )

render_footer()
