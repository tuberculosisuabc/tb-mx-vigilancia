import streamlit as st
import plotly.graph_objects as go
from db import get_data_overview
from utils import render_topnav, render_footer

st.set_page_config(
    page_title="SVG-TB-MX",
    page_icon="🫁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_topnav("Inicio")

# ── Header ────────────────────────────────────────────────────────────
st.markdown("""
    <h1>Tuberculosis en México · Vigilancia Genómica</h1>
    <p style='color:#4a6278;font-size:1.05rem;margin-bottom:0;line-height:1.7'>
        Sistema de vigilancia genómica de <i>Mycobacterium tuberculosis</i> en México a través de la
        integración de información disponible en
        <a href="https://www.ncbi.nlm.nih.gov/" target="_blank" style="color:#173b19 ;text-decoration:underline;">NCBI</a>
        y la implementación de
        <a href="https://tbdr.lshtm.ac.uk/" target="_blank" style="color:#173b19 ;text-decoration:underline;">TB Profiler</a>
        para el análisis genómico. Modelado realizado en 
        <a href='https://neo4j.com/' target='_blank' style='color:#173b19; text-decoration:underline;'>Neo4j</a> 
        y desarrollo de página web haciendo uso de 
        <a href='https://streamlit.io/' target='_blank' style='color:#173b19;text-decoration:underline;'>Streamlit</a>.
    </p>
""", unsafe_allow_html=True)

# ── Obtención de datos ────────────────────────────────────────────────
st.markdown("<div class='section-header'>Obtención y análisis de datos</div>", unsafe_allow_html=True)
st.markdown("""
    <p style='color:#4a6278;font-size:1rem;line-height:2'>
        1. Obtención de datos desde NCBI, aplicando filtros específicos para obtener muestras de Mtb proveniente de México<br>
        2. Extracción de metadata relevante y accesos a SRA<br>
        3. Análisis genómico de SRA disponibles implementando TB Profiler<br>
        4. Integración de metadata y resultados como nodos y relaciones para insertar en Neo4j<br>
        5. Análisis y visualización de datos a partir de queries
    </p>
""", unsafe_allow_html=True)

# ── Resumen General ───────────────────────────────────────────────────
st.markdown("<div class='section-header'>Resumen General</div>", unsafe_allow_html=True)

with st.spinner("Cargando datos..."):
    overview = get_data_overview()

ov1, ov2, ov3, ov4, ov5, ov6, ov7 = st.columns(7)
overview_cards = [
    (ov1, overview["total_biosamples"], "BioSamples totales", "kpi-green",
     "Muestras biológicas únicas registradas en NCBI"),
    (ov2, overview["total_sra_runs"],   "SRA disponibles",   "kpi-green",
     "Total de SRA Run IDs registrados en NCBI para México"),
    (ov3, overview["runs_processed"],   "Runs procesados",   "kpi-green",
     "Runs analizados con TB-Profiler v6"),
    (ov4, overview["qc_pass"],          "QC aprobado",       "kpi-green",
     "Runs con cobertura y mapeo suficiente"),
    (ov5, overview["mdr"],              "MDR-TB",            "kpi-amber",
     "Muestras con resistencia a rifampicina e isoniacida"),
    (ov6, overview["xdr"],              "XDR-TB",            "kpi-red",
     "Muestras con resistencia extensiva a fármacos"),
    (ov7, f"{overview['mdr_rate']}%",   "Tasa MDR",          "kpi-amber",
     "Porcentaje MDR sobre muestras con QC aprobado"),
]
for col, val, label, klass, tooltip in overview_cards:
    with col:
        st.markdown(f"""
        <div class='kpi-card {klass}' title="{tooltip}">
            <div class='kpi-value'>{val}</div>
            <div class='kpi-label'>{label}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Charts ────────────────────────────────────────────────────────────
ov_left, ov_right = st.columns([1.4, 1])

with ov_left:
    funnel_fig = go.Figure(go.Funnel(
        y=["BioSamples totales", "SRA disponibles", "Runs procesados", "QC aprobado"],
        x=[
            overview["total_biosamples"],
            overview["total_sra_runs"],
            overview["runs_processed"],
            overview["qc_pass"],
        ],
        textinfo="value+percent initial",
        marker=dict(color=["#2D6A4F", "#40916C", "#52B788", "#74C69D"]),
        connector=dict(line=dict(color="#C8C4BC", width=1)),
        textfont=dict(color="#FFFFFF", size=12),
    ))
    funnel_fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#3D5A4D", family="Poppins"),
        margin=dict(t=10, b=10, l=10, r=10),
        height=270,
    )
    st.plotly_chart(funnel_fig, use_container_width=True)

with ov_right:
    qc_pass     = overview["qc_pass"]
    qc_fail     = overview["qc_fail"]
    no_mtb      = overview.get("no_mtb", 0)
    failed_proc = overview.get("failed_processing", 0)
    empty_runs  = overview.get("empty_runs", 0)
    total_runs  = overview["total_sra_runs"]

    labels = ["QC aprobado", "QC rechazado", "No-Mtb", "No procesados", "Runs vacíos"]
    values = [qc_pass, qc_fail, no_mtb, failed_proc, empty_runs]
    colors = ["#2D6A4F", "#D4A017", "#8B7355", "#C44B2B", "#B0A898"]
    custom_text = [f"{round(v / total_runs * 100, 1)}%" for v in values]

    qc_fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        hole=0.5,
        text=custom_text,
        textinfo="text",
        hovertemplate="<b>%{label}</b><br>%{value} runs<br>%{text} de SRA disponibles<extra></extra>",
        marker=dict(
            colors=colors,
            line=dict(color="#F4F1EA", width=2),
        ),
        textposition="outside",
        textfont_size=10,
    ))
    qc_fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#3D5A4D", family="Poppins"),
        legend=dict(orientation="v", bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        margin=dict(t=10, b=10, l=10, r=10),
        height=270,
        annotations=[dict(
            text=f"<b>{total_runs}</b><br>SRA runs",
            x=0.5, y=0.5, font_size=11, font_color="#1B3A2D",
            showarrow=False,
        )],
    )
    st.plotly_chart(qc_fig, use_container_width=True)

    st.markdown(f"""
    <div style='font-size:0.78rem;color:#6b7f93;line-height:1.9;padding:0 8px'>
        <b>{empty_runs}</b> ({round(empty_runs/total_runs*100,1)}%) Runs sin datos en SRA (spots = 0)<br>
        <b>{failed_proc}</b> ({round(failed_proc/total_runs*100,1)}%) Runs con error en TB-Profiler<br>
        <b>{no_mtb}</b> ({round(no_mtb/total_runs*100,1)}%) Runs sin <i>M. tuberculosis</i> confirmado<br>
        <b>{qc_fail}</b> ({round(qc_fail/total_runs*100,1)}%) Runs con baja cobertura o mapeo insuficiente<br>
        <b>{qc_pass}</b> ({round(qc_pass/total_runs*100,1)}%) Runs con QC aprobado ✓
    </div>
    """, unsafe_allow_html=True)

render_footer()
