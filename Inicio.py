import plotly.graph_objects as go
import streamlit as st

from db import get_data_overview
from utils import BG, TEXT_DARK, page_header, render_footer, section, setup_page, show_fig, style_fig

setup_page("Inicio")

page_header(
    "Tuberculosis en México · Vigilancia Genómica",
    """Sistema de vigilancia genómica de <i>Mycobacterium tuberculosis</i> en México a través de la
    integración de información disponible en
    <a href="https://www.ncbi.nlm.nih.gov/" target="_blank">NCBI</a>
    y la implementación de
    <a href="https://tbdr.lshtm.ac.uk/" target="_blank">TB-Profiler</a>
    para el análisis genómico. Modelado realizado en
    <a href="https://neo4j.com/" target="_blank">Neo4j</a>
    y desarrollo de página web haciendo uso de
    <a href="https://streamlit.io/" target="_blank">Streamlit</a>.""",
    sample_size=False,
)

# ── Obtención de datos ───────────────────────────────────────────────
section("Obtención y análisis de datos")
st.markdown("""
    <p class='texto' style='line-height:2'>
        1. Obtención de datos desde NCBI, aplicando filtros específicos para obtener muestras de <i>M. tuberculosis</i> provenientes de México<br>
        2. Extracción de metadata relevante y accesos a SRA<br>
        3. Análisis genómico de los runs de SRA disponibles con TB-Profiler; si una muestra tiene varios runs, se usa el de mejor calidad<br>
        4. Integración de metadata y resultados como nodos y relaciones para insertar en Neo4j<br>
        5. Análisis y visualización de datos a partir de queries
    </p>
""", unsafe_allow_html=True)

# ── Resumen general ──────────────────────────────────────────────────
section("Resumen General")

with st.spinner("Cargando datos..."):
    overview = get_data_overview()

# (valor, etiqueta, clase de color, descripción al pasar el cursor)
overview_cards = [
    (overview["total_biosamples"], "BioSamples",        "kpi-green",
     "Muestras biológicas de M. tuberculosis de México con al menos un run en SRA"),
    (overview["with_data"],        "Con lecturas",      "kpi-green",
     "BioSamples con lecturas disponibles en SRA"),
    (overview["processed"],        "Analizados",        "kpi-green",
     "BioSamples analizados con TB-Profiler v6 (se usa el mejor run de cada uno)"),
    (overview["qc_pass"],          "QC aprobado",       "kpi-green",
     "BioSamples con cobertura y mapeo suficiente"),
    (overview["mdr"],              "TB-MDR",            "kpi-amber",
     "Muestras con resistencia a rifampicina e isoniacida"),
    (overview["xdr"],              "TB-XDR",            "kpi-red",
     "Muestras con resistencia extensiva a fármacos"),
    (f"{overview['mdr_rate']}%",   "Tasa TB-MDR",       "kpi-amber",
     "Porcentaje de TB-MDR sobre los genomas con QC aprobado"),
]
for col, (val, label, klass, tooltip) in zip(st.columns(len(overview_cards)), overview_cards):
    col.markdown(f"""
    <div class='kpi-card {klass}' title="{tooltip}">
        <div class='kpi-value'>{val}</div>
        <div class='kpi-label'>{label}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Gráficas ─────────────────────────────────────────────────────────
ov_left, ov_right = st.columns([1.4, 1])

with ov_left:
    funnel_fig = go.Figure(go.Funnel(
        y=["BioSamples", "Con lecturas", "Analizados", "QC aprobado"],
        x=[overview["total_biosamples"], overview["with_data"],
           overview["processed"], overview["qc_pass"]],
        textinfo="value+percent initial",
        marker=dict(color=["#2D6A4F", "#40916C", "#52B788", "#74C69D"]),
        connector=dict(line=dict(color="#C8C4BC", width=1)),
        textfont=dict(color="#FFFFFF", size=12),
    ))
    show_fig(style_fig(funnel_fig, height=270))

with ov_right:
    total = overview["total_biosamples"]
    # (etiqueta, número de BioSamples, color, descripción para la lista de abajo).
    # Los grupos no se traslapan y suman el total de BioSamples.
    groups = [
        ("QC aprobado",    overview["qc_pass"] - overview["no_mtb"], "#2D6A4F",
         "BioSamples de <i>M. tuberculosis</i> con QC aprobado ✓"),
        ("QC rechazado",   overview["qc_fail"],                      "#D4A017",
         "BioSamples con baja cobertura o mapeo insuficiente"),
        ("M. bovis / BCG", overview["no_mtb"],                       "#8B7355",
         "BioSamples de <i>M. bovis</i> / BCG (complejo <i>M. tuberculosis</i>)"),
        ("No procesados",  overview["failed"],                       "#C44B2B",
         "BioSamples con error en la descarga o en TB-Profiler"),
        ("Sin lecturas",   overview["no_data"],                      "#B0A898",
         "BioSamples cuyos runs no tienen datos en SRA (spots = 0)"),
    ]

    def pct(v):
        return round(v / total * 100, 1) if total else 0

    qc_fig = go.Figure(go.Pie(
        labels=[g[0] for g in groups],
        values=[g[1] for g in groups],
        hole=0.5,
        text=[f"{pct(g[1])}%" for g in groups],
        textinfo="text",
        hovertemplate="<b>%{label}</b><br>%{value} BioSamples<br>%{text} del total<extra></extra>",
        marker=dict(colors=[g[2] for g in groups], line=dict(color=BG, width=2)),
        textposition="outside",
        textfont_size=10,
    ))
    style_fig(qc_fig, height=270, legend=dict(orientation="v", font=dict(size=10)),
              annotations=[dict(text=f"<b>{total}</b><br>BioSamples", x=0.5, y=0.5,
                                font_size=11, font_color=TEXT_DARK, showarrow=False)])
    show_fig(qc_fig)

    # Misma información en texto, del grupo más pequeño al más grande
    lines = "<br>".join(f"<b>{v}</b> ({pct(v)}%) {desc}" for _, v, _, desc in reversed(groups))
    st.markdown(f"<div class='texto-nota'>{lines}</div>", unsafe_allow_html=True)

render_footer()
