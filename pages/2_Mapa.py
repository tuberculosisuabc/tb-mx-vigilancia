import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from db import get_cases_by_state
from utils import BG, TEXT_DARK, TEXT_MUTED, page_header, render_footer, section, setup_page, show_fig, style_fig

setup_page("Mapa")

page_header(
    "Distribución Territorial de Tuberculosis",
    """Mapa interactivo que muestra la distribución geográfica de muestras de tuberculosis por estado,
    con filtros para visualizar el total de genomas y los casos TB-MDR y TB-XDR.""",
)

# ── Controles del mapa ───────────────────────────────────────────────
METRICS = {"Total de muestras": "total", "Casos TB-MDR": "mdr", "Casos TB-XDR": "xdr"}
metric = st.radio("Métrica", options=list(METRICS), horizontal=True)
metric_col = METRICS[metric]

with st.spinner("Cargando mapa..."):
    df = pd.DataFrame(get_cases_by_state())

# ── Mapa ─────────────────────────────────────────────────────────────
fig = go.Figure(go.Scattergeo(
    lat=df["lat"],
    lon=df["lon"],
    text=df["state"],
    hovertext=df.apply(lambda r: (
        f"<b>{r['state']}</b><br>Total: {r['total']}<br>TB-MDR: {r['mdr']}<br>TB-XDR: {r['xdr']}"
    ), axis=1),
    hoverinfo="text",
    marker=dict(
        size=df[metric_col] ** 0.55 * 5,
        color=df[metric_col],
        colorscale="YlOrRd",
        showscale=True,
        colorbar=dict(
            title=dict(text=metric, font=dict(color=TEXT_MUTED)),
            thickness=12,
            len=0.5,
            bgcolor="rgba(0,0,0,0)",
            tickfont=dict(color=TEXT_MUTED),
        ),
        line=dict(color=TEXT_DARK, width=1),
        opacity=0.85,
        sizemode="area",
        sizemin=6,
    ),
    mode="markers+text",
    textposition="top center",
    textfont=dict(color=TEXT_DARK, size=9),
))
fig.update_geos(
    visible=True,
    resolution=50,
    showcountries=True,
    countrycolor="#C8C4BC",
    showcoastlines=True,
    coastlinecolor="#C8C4BC",
    showland=True,
    landcolor="#93bf96",
    showocean=True,
    oceancolor="#93bcbf",
    showlakes=False,
    lataxis_range=[13, 33],
    lonaxis_range=[-120, -85],
    bgcolor=BG,
)
style_fig(fig, height=520, margin=dict(t=10, b=10, l=0, r=0))
fig.update_layout(paper_bgcolor=BG)   # el mapa lleva el fondo del sitio, no transparente
show_fig(fig)

# ── Tabla por estado ─────────────────────────────────────────────────
section("Datos por Estado")

df_display = df[["state", "total", "mdr", "xdr"]].copy()
df_display["mdr_rate"] = (df_display["mdr"] / df_display["total"] * 100).round(1).astype(str) + "%"
df_display.columns = ["Estado", "Total", "TB-MDR", "TB-XDR", "Tasa TB-MDR"]
df_display = df_display.sort_values("Total", ascending=False).reset_index(drop=True)

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Total":  st.column_config.NumberColumn("Total"),
        "TB-MDR": st.column_config.NumberColumn("TB-MDR", format="%d"),
        "TB-XDR": st.column_config.NumberColumn("TB-XDR", format="%d"),
    },
)

render_footer()
