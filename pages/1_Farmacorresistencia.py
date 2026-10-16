import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import get_drug_resistance_counts, get_resistance_profile
from utils import (AXIS_GRID, AXIS_PLAIN, BG, DRTYPE_COLORS, DRTYPE_DESCRIPTIONS,
                   DRUG_CLASS_COLORS, DRUG_CLASS_LABELS, TEXT_DARK, TEXT_MUTED, drtype_es,
                   drug_es, page_header, render_footer, section, setup_page, show_fig, style_fig)

setup_page("Farmacorresistencia")

page_header(
    "Perfil de Farmacorresistencia Genotípica",
    """Farmacorresistencia genotípica evaluada con TB-Profiler v6 a partir de datos de secuenciación de
    genoma completo (WGS). Se incluyen únicamente muestras que aprobaron el filtro de calidad
    (cobertura ≥ 10× y mapeo ≥ 90%). La clasificación sigue los criterios del
    <a href="https://www.who.int/publications/i/item/9789240082410" target="_blank">Catálogo de
    mutaciones de la OMS</a>.""",
)

# ── Clasificación de resistencia ─────────────────────────────────────
section(
    "Clasificación de farmacorresistencia",
    """Distribución de los genomas con QC aprobado según su clasificación de resistencia definida
    por la OMS. Cada muestra se asigna a una única categoría según el patrón de resistencia detectado.""",
)

col_left, col_right = st.columns([1, 1])

with col_left:
    df_res = pd.DataFrame(get_resistance_profile())
    df_res["drtype"] = df_res["drtype"].map(drtype_es)
    # De menor a mayor resistencia, en el mismo orden que la tabla de la derecha
    orden = list(DRTYPE_COLORS)
    df_res = df_res.sort_values("drtype", key=lambda c: c.map(lambda d: orden.index(d) if d in orden else 99))

    fig = px.pie(df_res, values="count", names="drtype",
                 color="drtype", color_discrete_map=DRTYPE_COLORS, hole=0.55)
    fig.update_traces(sort=False, direction="clockwise", textposition="outside", textfont_size=11,
                      marker=dict(line=dict(color=BG, width=2)))
    style_fig(fig, height=420, margin=dict(t=30, b=30, l=30, r=30), legend=dict(orientation="v"),
              annotations=[dict(text=f"<b>{df_res['count'].sum()}</b><br>muestras", x=0.5, y=0.5,
                                font_size=14, font_color=TEXT_DARK, showarrow=False)])
    show_fig(fig)

with col_right:
    filas = "".join(
        f"<tr style='border-bottom:1px solid #C8C4BC'>"
        f"<td style='padding:10px 8px;font-weight:600;color:{DRTYPE_COLORS[cat]}'>{cat}</td>"
        f"<td style='padding:10px 8px;color:{TEXT_MUTED}'>{desc}</td></tr>"
        for cat, desc in DRTYPE_DESCRIPTIONS.items()
    )
    st.markdown(
        "<div style='padding:2rem 1rem 0 1rem'>"
        f"<table style='width:100%;border-collapse:collapse;font-size:0.92rem'>{filas}</table>"
        "</div>",
        unsafe_allow_html=True,
    )

# ── Resistencia por fármaco ──────────────────────────────────────────
df_drug = pd.DataFrame(get_drug_resistance_counts())
df_drug["color"]   = df_drug["drug_class"].map(DRUG_CLASS_COLORS).fillna(DRUG_CLASS_COLORS["other"])
df_drug["clase"]   = df_drug["drug_class"].map(DRUG_CLASS_LABELS).fillna("Otros")
df_drug["farmaco"] = df_drug["drug"].map(drug_es)

# Leyenda solo con las clases presentes en los datos
leyenda = " &nbsp; ".join(
    f"<span style='color:{DRUG_CLASS_COLORS[c]}'>■</span> {DRUG_CLASS_LABELS[c]}"
    for c in DRUG_CLASS_LABELS if c in set(df_drug["drug_class"])
)
section(
    "Resistencia por Fármaco",
    """Número de muestras con al menos una variante de resistencia genotípica para cada fármaco.
    Una misma muestra puede contribuir a múltiples fármacos.""",
)
st.markdown(f"<p class='texto'>El color indica la clasificación de la OMS (2022): {leyenda}</p>",
            unsafe_allow_html=True)

fig2 = go.Figure(go.Bar(
    x=df_drug["count"],
    y=df_drug["farmaco"],
    orientation="h",
    marker_color=df_drug["color"],
    text=df_drug["count"],
    textposition="outside",
    textfont=dict(color=TEXT_MUTED, size=11),
    customdata=df_drug[["clase"]].values,
    hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>Muestras: %{x}<extra></extra>",
))
style_fig(fig2, height=420, margin=dict(t=10, b=10, l=10, r=60),
          xaxis=AXIS_GRID, yaxis=dict(AXIS_PLAIN, autorange="reversed"))
show_fig(fig2)

render_footer()
