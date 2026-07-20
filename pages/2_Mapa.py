import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from db import get_cases_by_state
from utils import render_topnav, render_footer, render_sample_size

st.set_page_config(
    page_title="Mapa · SVG-TB-MX",
    page_icon="🫁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_topnav("Mapa")

# ── Header ────────────────────────────────────────────────────────────
st.markdown("""
    <h1>Distribución Territorial de Tuberculosis</h1>
    <p style='color:#4a6278;font-size:1.05rem;line-height:1.7'>
        Mapa interactivo que muestra la distribución geográfica de muestras de tuberculosis por estado,
        con filtros para visualizar casos totales, MDR y XDR.
    </p>
""", unsafe_allow_html=True)

render_sample_size()

# ── Map controls ──────────────────────────────────────────────────────
metric = st.radio(
    "Métrica",
    options=["Total de muestras", "Casos MDR", "Casos XDR"],
    horizontal=True,
)

with st.spinner("Cargando mapa..."):
    data = get_cases_by_state()

df = pd.DataFrame(data)
metric_col = {"Total de muestras": "total", "Casos MDR": "mdr", "Casos XDR": "xdr"}[metric]

fig = go.Figure()
fig.add_trace(go.Scattergeo(
    lat=df["lat"],
    lon=df["lon"],
    text=df["state"],
    hovertext=df.apply(lambda r: (
        f"<b>{r['state']}</b><br>Total: {r['total']}<br>MDR: {r['mdr']}<br>XDR: {r['xdr']}"
    ), axis=1),
    hoverinfo="text",
    marker=dict(
        size=df[metric_col] ** 0.55 * 5,
        color=df[metric_col],
        colorscale="YlOrRd",
        showscale=True,
        colorbar=dict(
            title=dict(text=metric, font=dict(color="#3D5A4D")),
            thickness=12,
            len=0.5,
            bgcolor="rgba(0,0,0,0)",
            tickfont=dict(color="#3D5A4D"),
        ),
        line=dict(color="#1B3A2D", width=1),
        opacity=0.85,
        sizemode="area",
        sizemin=6,
    ),
    mode="markers+text",
    textposition="top center",
    textfont=dict(color="#1B3A2D", size=9),
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
    bgcolor="#F4F1EA",
)
fig.update_layout(
    paper_bgcolor="#F4F1EA",
    geo=dict(bgcolor="#F4F1EA"),
    font=dict(color="#3D5A4D", family="Poppins"),
    margin=dict(t=10, b=10, l=0, r=0),
    height=520,
)
st.plotly_chart(fig, use_container_width=True)

# ── Data table ────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>Datos por Estado</div>", unsafe_allow_html=True)

df_display = df[["state", "total", "mdr", "xdr"]].copy()
df_display["mdr_rate"] = (df_display["mdr"] / df_display["total"] * 100).round(1).astype(str) + "%"
df_display.columns = ["Estado", "Total", "MDR", "XDR", "Tasa MDR"]
df_display = df_display.sort_values("Total", ascending=False).reset_index(drop=True)

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Total": st.column_config.NumberColumn("Total"),
        "MDR":   st.column_config.NumberColumn("MDR", format="%d"),
        "XDR":   st.column_config.NumberColumn("XDR", format="%d"),
    }
)

render_footer()
