import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from db import get_resistance_profile, get_drug_resistance_counts
from utils import render_topnav, render_footer, render_sample_size

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
    <p style='color:#4a6278;font-size:1.05rem;margin-bottom:0;line-height:1.7'>
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
    <p style='color:#4a6278;font-size:1rem;margin-bottom:0'>
    Distribución de los genomas con QC aprobado según su clasificación de resistencia definida por la OMS.
    Cada muestra se asigna a una única categoría según el patrón de resistencia detectado.
    </p>
""", unsafe_allow_html=True)

col_left, col_right = st.columns([1, 1])

with col_left:
    res_data = get_resistance_profile()
    df_res = pd.DataFrame(res_data)
    color_map = {
        "Sensitive":    "#22c55e",
        "HR-TB":        "#facc15",
        "MDR-TB":       "#f97316",
        "RR-TB":        "#fb923c",
        "Pre-XDR-TB":   "#ef4444",
        "XDR-TB":       "#dc2626",
        "Other":        "#64748b",
        "Low_coverage": "#334155",
        "No-Mtb":       "#a855f7",
    }
    fig = px.pie(
        df_res, values="count", names="drtype",
        color="drtype", color_discrete_map=color_map,
        hole=0.55,
    )
    fig.update_traces(
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
    st.markdown("""
    <div style='padding:2rem 1rem 0 1rem'>
        <table style='width:100%;border-collapse:collapse;font-size:0.92rem'>
            <tr style='border-bottom:1px solid #C8C4BC'>
                <td style='padding:10px 8px;font-weight:600;color:#22c55e'>Sensitive</td>
                <td style='padding:10px 8px;color:#4a6278'>Sin variantes de resistencia detectadas</td>
            </tr>
            <tr style='border-bottom:1px solid #C8C4BC'>
                <td style='padding:10px 8px;font-weight:600;color:#facc15'>HR-TB</td>
                <td style='padding:10px 8px;color:#4a6278'>Resistencia a isoniacida (sin RIF)</td>
            </tr>
            <tr style='border-bottom:1px solid #C8C4BC'>
                <td style='padding:10px 8px;font-weight:600;color:#fb923c'>RR-TB</td>
                <td style='padding:10px 8px;color:#4a6278'>Resistencia a rifampicina</td>
            </tr>
            <tr style='border-bottom:1px solid #C8C4BC'>
                <td style='padding:10px 8px;font-weight:600;color:#f97316'>MDR-TB</td>
                <td style='padding:10px 8px;color:#4a6278'>Resistencia a rifampicina <b>+</b> isoniacida</td>
            </tr>
            <tr style='border-bottom:1px solid #C8C4BC'>
                <td style='padding:10px 8px;font-weight:600;color:#ef4444'>Pre-XDR-TB</td>
                <td style='padding:10px 8px;color:#4a6278'>MDR/RR-TB <b>+</b> fluoroquinolona</td>
            </tr>
            <tr style='border-bottom:1px solid #C8C4BC'>
                <td style='padding:10px 8px;font-weight:600;color:#dc2626'>XDR-TB</td>
                <td style='padding:10px 8px;color:#4a6278'>Pre-XDR-TB <b>+</b> bedaquilina y/o linezolid</td>
            </tr>
            <tr style='border-bottom:1px solid #C8C4BC'>
                <td style='padding:10px 8px;font-weight:600;color:#64748b'>Other</td>
                <td style='padding:10px 8px;color:#4a6278'>Patrón de resistencia no clasificable</td>
            </tr>
            <tr>
                <td style='padding:10px 8px;font-weight:600;color:#a855f7'>No-Mtb</td>
                <td style='padding:10px 8px;color:#4a6278'>Linaje no perteneciente a <i>M. tuberculosis</i> complex</td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

# ── Resistencia por fármaco ───────────────────────────────────────────
st.markdown("<div class='section-header'>Resistencia por Fármaco</div>", unsafe_allow_html=True)
st.markdown("""
    <p style='color:#4a6278;font-size:1rem;margin-bottom:12px'>
        Número de muestras con al menos una variante de resistencia genotípica para cada fármaco.
        Una misma muestra puede contribuir a múltiples fármacos.</p>
    <p style='color:#4a6278;font-size:1rem;margin-bottom:12px'>
        El color indica la clase terapéutica según la OMS:
        <span style='color:#f87171'>■</span> Primera línea &nbsp;
        <span style='color:#fb923c'>■</span> Fluoroquinolonas &nbsp;
        <span style='color:#e879f9'>■</span> Grupo A &nbsp;
        <span style='color:#a78bfa'>■</span> Grupo B &nbsp;
        <span style='color:#60a5fa'>■</span> Inyectables 2ª línea &nbsp;
        <span style='color:#f59e0b'>■</span> Inyectables 1ª línea &nbsp;
        <span style='color:#64748b'>■</span> Otros
    </p>
""", unsafe_allow_html=True)

drug_data = get_drug_resistance_counts()
df_drug = pd.DataFrame(drug_data)
class_colors = {
    "1st_line":            "#f87171",
    "fluoroquinolone":     "#fb923c",
    "group_A":             "#e879f9",
    "group_B":             "#a78bfa",
    "2nd_line_injectable": "#60a5fa",
    "1st_line_injectable": "#f59e0b",
    "other":               "#64748b",
}
df_drug["color"] = df_drug["drug_class"].map(class_colors).fillna("#F20707")

fig2 = go.Figure(go.Bar(
    x=df_drug["count"],
    y=df_drug["drug"],
    orientation="h",
    marker_color=df_drug["color"],
    text=df_drug["count"],
    textposition="outside",
    textfont=dict(color="#3D5A4D", size=11),
))
fig2.update_layout(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#3D5A4D", family="Poppins"),
    xaxis=dict(showgrid=True, gridcolor="#D5D0C4", color="#4a6278"),
    yaxis=dict(showgrid=False, autorange="reversed", color="#3D5A4D"),
    margin=dict(t=10, b=10, l=10, r=60),
    height=420,
)
st.plotly_chart(fig2, use_container_width=True)

render_footer()
