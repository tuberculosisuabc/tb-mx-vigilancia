# Página principal del sitio web

import plotly.graph_objects as go  #para gráficas interactivas
import streamlit as st  #se contruye la página en Streamlit
from db import get_data_overview # Consulta de Neo4j 
from utils import BG, TEXT_DARK, page_header, render_footer, section, setup_page, show_fig, style_fig # componentes compartidos de la página

setup_page("Inicio") # Configura la pestaña, estilos, encabezado y barra de navegación
page_header( #Titulo e introducción
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
    sample_size=False,  #no se muestra tamaño de muestra
)

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

section("Resumen General")
with st.spinner("Cargando datos..."):
    overview = get_data_overview() #Conteos

overview_cards = [ # (valor, etiqueta, clase de color, descripción al pasar el cursor)
    (overview["total_biosamples"], "BioSamples",        "kpi-green",
     "Muestras biológicas de M. tuberculosis de México registradas en NCBI, con o sin run en SRA"),
    (overview["with_data"],        "Con lecturas",      "kpi-green",
     "BioSamples con lecturas disponibles en SRA"),
    (overview["processed"],        "Analizados",        "kpi-green",
     "BioSamples analizados con TB-Profiler v6 (se usa el mejor run de cada uno)"),
    (overview["qc_pass"],          "QC aprobado",       "kpi-green",
     "Genomas de M. tuberculosis con cobertura y mapeo suficiente (base de todos los análisis)"),
    (overview["mdr"],              "TB-MDR",            "kpi-amber",
     "Muestras con resistencia a rifampicina e isoniacida"),
    (overview["xdr"],              "TB-XDR",            "kpi-red",
     "Muestras con resistencia extensiva a fármacos"),
    (f"{overview['mdr_rate']}%",   "Tasa TB-MDR",       "kpi-amber",
     "Porcentaje de TB-MDR sobre los genomas con QC aprobado"),
]
# Crea una columna por tarjeta y dibuja cada tarjeta con HTML.
for col, (val, label, klass, tooltip) in zip(st.columns(len(overview_cards)), overview_cards):
    col.markdown(f"""
    <div class='kpi-card {klass}' title="{tooltip}">
        <div class='kpi-value'>{val}</div>
        <div class='kpi-label'>{label}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Gráficas 
ov_left, ov_right = st.columns([1.4, 1]) #dos columnas

with ov_left: # Filtrado de  BioSamples despues de cada etapa 
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
    groups = [  # Los grupos  suman el total de BioSamples (etiqueta, conteo, color, descripción)
        ("QC aprobado", overview["qc_pass"],"#2D6A4F", "BioSamples de <i>M. tuberculosis</i> con QC aprobado ✓"),
        ("QC rechazado", overview["qc_fail"], "#D4A017", "BioSamples con baja cobertura o mapeo insuficiente"),
        ("No M. tuberculosis", overview["no_mtb"], "#8B7355", "BioSamples no M. tuberculosis, excluidos de los análisis"),
        ("No procesados", overview["failed"], "#C44B2B", "BioSamples con error en la descarga o en TB-Profiler"),
        ("Sin lecturas", overview["no_data"], "#B0A898", "BioSamples cuyos runs no tienen datos en SRA (spots = 0)"),
        ("Sin run en SRA", overview.get("no_run", 0), "#D8D2C8", "BioSamples sin run de secuenciación (WGS) publicado en SRA"),
    ]

    def pct(v): # Porcentaje que representan
        return round(v / total * 100, 1) if total else 0

    qc_fig = go.Figure(go.Pie(   # Gráfica de dona con los grupos de arriba.
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

# Pie de página con fuentes de datos y fecha de la última actualización.
render_footer()
