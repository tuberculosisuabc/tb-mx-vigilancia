import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from db import get_resistance_profile, get_drug_resistance_counts
from utils import render_topnav, render_footer, render_sample_size
from utils import (DRTYPE_COLORS, DRTYPE_DESCRIPTIONS, DRUG_CLASS_COLORS,
                   DRUG_CLASS_LABELS, drtype_es, drug_es)

st.set_page_config(
    page_title="Farmacorresistencia · SVG-TB-MX",
    page_icon="🫁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_topnav("Farmacorresistencia")

# ── Header ────────────────────────────────────────────────────────────

st.markdown("""
    <h1>Perfil de Farmacorresistencia Genotípica</h1>
    <p style='color:#3D5A4D;font-size:1.05rem;margin-bottom:0;line-height:1.7'>
        Farmacorresistencia genotípica evaluada con TB-Profiler v6 a partir de datos de secuenciación de
        genoma completo (WGS). Se incluyen únicamente muestras que aprobaron el filtro de calidad
        (cobertura ≥ 10× y mapeo ≥ 90%). La clasificación sigue los criterios del
        <a href="https://www.who.int/publications/i/item/9789240082410" target="_blank"
           style="color:#2D6A4F;text-decoration:underline;">Catálogo de mutaciones de la OMS</a>. <br>
    </p>
""", unsafe_allow_html=True)

render_sample_size()

# ── Clasificación de resistencia ──────────────────────────────────────
st.markdown("<div class='section-header'>Clasificación de farmacorresistencia</div>", unsafe_allow_html=True)
st.markdown("""
    <p style='color:#3D5A4D;font-size:1rem;margin-bottom:0'>
    Distribución de los genomas con QC aprobado según su clasificación de resistencia definida por la OMS.
    Cada muestra se asigna a una única categoría según el patrón de resistencia detectado.
    </p>
""", unsafe_allow_html=True)

col_left, col_right = st.columns([1, 1])

with col_left:
    res_data = get_resistance_profile()
    df_res = pd.DataFrame(res_data)
    df_res["drtype"] = df_res["drtype"].map(drtype_es)
    # De menor a mayor resistencia, en el mismo orden que la tabla de la derecha
    orden = list(DRTYPE_COLORS)
    df_res = df_res.sort_values("drtype", key=lambda c: c.map(lambda d: orden.index(d) if d in orden else 99))
    fig = px.pie(
        df_res, values="count", names="drtype",
        color="drtype", color_discrete_map=DRTYPE_COLORS,
        hole=0.55,
    )
    fig.update_traces(
        sort=False, direction="clockwise",
        textposition="outside",
        textfont_size=11,
        marker=dict(line=dict(color="#F4F1EA", width=2)),
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#3D5A4D", family="Poppins"),
        legend=dict(orientation="v", bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        margin=dict(t=30, b=30, l=30, r=30),
        height=420,
        annotations=[dict(
            text=f"<b>{df_res['count'].sum()}</b><br>muestras",
            x=0.5, y=0.5, font_size=14, font_color="#1B3A2D",
            showarrow=False,
        )],
    )
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    filas = "".join(
        f"<tr style='border-bottom:1px solid #C8C4BC'>"
        f"<td style='padding:10px 8px;font-weight:600;color:{DRTYPE_COLORS[cat]}'>{cat}</td>"
        f"<td style='padding:10px 8px;color:#3D5A4D'>{desc}</td></tr>"
        for cat, desc in DRTYPE_DESCRIPTIONS.items()
    )
    st.markdown(
        "<div style='padding:2rem 1rem 0 1rem'>"
        f"<table style='width:100%;border-collapse:collapse;font-size:0.92rem'>{filas}</table>"
        "</div>",
        unsafe_allow_html=True,
    )

# ── Resistencia por fármaco ───────────────────────────────────────────
st.markdown("<div class='section-header'>Resistencia por Fármaco</div>", unsafe_allow_html=True)
drug_data = get_drug_resistance_counts()
df_drug = pd.DataFrame(drug_data)
df_drug["color"] = df_drug["drug_class"].map(DRUG_CLASS_COLORS).fillna(DRUG_CLASS_COLORS["other"])
df_drug["clase"] = df_drug["drug_class"].map(DRUG_CLASS_LABELS).fillna("Otros")
df_drug["farmaco"] = df_drug["drug"].map(drug_es)

# Leyenda solo con las clases presentes en los datos
leyenda = " &nbsp; ".join(
    f"<span style='color:{DRUG_CLASS_COLORS[c]}'>■</span> {DRUG_CLASS_LABELS[c]}"
    for c in DRUG_CLASS_LABELS if c in set(df_drug["drug_class"])
)
st.markdown(f"""
    <p style='color:#3D5A4D;font-size:1rem;margin-bottom:12px'>
        Número de muestras con al menos una variante de resistencia genotípica para cada fármaco.
        Una misma muestra puede contribuir a múltiples fármacos.</p>
    <p style='color:#3D5A4D;font-size:1rem;margin-bottom:12px'>
        El color indica la clasificación de la OMS (2022): {leyenda}
    </p>
""", unsafe_allow_html=True)

fig2 = go.Figure(go.Bar(
    x=df_drug["count"],
    y=df_drug["farmaco"],
    orientation="h",
    marker_color=df_drug["color"],
    text=df_drug["count"],
    textposition="outside",
    textfont=dict(color="#3D5A4D", size=11),
    customdata=df_drug[["clase"]].values,
    hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>Muestras: %{x}<extra></extra>",
))
fig2.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#3D5A4D", family="Poppins"),
    xaxis=dict(showgrid=True, gridcolor="#D5D0C4", color="#3D5A4D"),
    yaxis=dict(showgrid=False, autorange="reversed", color="#3D5A4D"),
    margin=dict(t=10, b=10, l=10, r=60),
    height=420,
)
st.plotly_chart(fig2, use_container_width=True)

render_footer()
