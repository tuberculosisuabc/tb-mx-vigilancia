import streamlit as st
from utils import render_topnav, render_footer

st.set_page_config(
    page_title="Acerca del Proyecto · SVG-TB-MX",
    page_icon="🫁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_topnav("Acerca del Proyecto")

# ── Header ────────────────────────────────────────────────────────────
st.markdown("""
    <h1>Acerca del Proyecto</h1>
    <p style='color:#4a6278;font-size:1.05rem;line-height:1.7'>
        Este dashboard forma parte de un esfuerzo colaborativo de vigilancia genómica de
        <i>Mycobacterium tuberculosis</i> en México, desarrollado en el marco del Centro de Investigación,
        Innovación y Vigilancia Genómica de Enfermedades Infecciosas (CIIViGEI) de la Universidad
        Autónoma de Baja California (UABC), Ensenada, Baja California, México.
    </p>
""", unsafe_allow_html=True)

# ── Equipo ────────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>Equipo de Trabajo</div>", unsafe_allow_html=True)
st.markdown("""
    <p style='color:#4a6278;font-size:1rem;line-height:1.9'>
    <b>Dra. Raquel Muñiz-Salazar — Colaboradora Nacional</b><br>
    &nbsp;&nbsp;• Profesora-Investigadora, Escuela de Ciencias de la Salud, UABC<br>
    &nbsp;&nbsp;• Coordinadora de Investigación y Posgrado, ECS-UABC<br>
    &nbsp;&nbsp;• Coordinadora del CIIViGEI, UABC<br>
    &nbsp;&nbsp;• Presidenta de The Union Latinoamérica (2023–2026)<br>
    &nbsp;&nbsp;• Presidenta de RemiTB<br><br>

    <p style='color:#4a6278;font-size:1rem;line-height:1.9'>
    <b>Dr. Giuseppe Pirrò — Colaborador Internacional</b><br>
    &nbsp;&nbsp;• Profesor Asociado, Ciencias de la Computación, Università della Calabria, Italia<br>
    &nbsp;&nbsp;• Departamento DEMACS (Ingegneria Informatica, Modellistica, Elettronica e Sistemistica)<br>
    &nbsp;&nbsp;• Áreas: Web Semántica, Bases de datos orientado a grafos, Knowledge Graphs, Sistemas distribuidos<br><br>

    <p style='color:#4a6278;font-size:1rem;line-height:1.9'>
    <b>Ing. Daniela Santana Camacho — Desarrollo y análisis de datos</b><br>
    &nbsp;&nbsp;• Bioingeniera, Universidad Autónoma de Baja California<br>
    &nbsp;&nbsp;• Estudiante de posgrado en Biotecnología de la Salud, DiBEST, Università della Calabria, Italia
    </p>
""", unsafe_allow_html=True)

# ── Recursos ──────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>Recursos utilizados</div>", unsafe_allow_html=True)
st.markdown("""
    <p style='color:#4a6278;font-size:1rem;line-height:2.2'>
    • <a href='https://www.ncbi.nlm.nih.gov/' target='_blank' style='color:#2D6A4F;text-decoration:underline;'>NCBI</a>: Recopilación de muestras y genomas<br>
    • <a href='https://github.com/jodyphelan/TBProfiler' target='_blank' style='color:#2D6A4F;text-decoration:underline;'>TB-Profiler</a>: Análisis genómico<br>
    • <a href='https://www.who.int/publications/i/item/9789240082410' target='_blank' style='color:#2D6A4F;text-decoration:underline;'>Catálogo de mutaciones de la OMS</a>: Clasificación de mutaciones y farmacorresistencia<br>
    • <a href='https://neo4j.com/' target='_blank' style='color:#2D6A4F;text-decoration:underline;'>Neo4j</a>: Base de datos orientada a grafos<br>
    • <a href='https://streamlit.io/' target='_blank' style='color:#2D6A4F;text-decoration:underline;'>Streamlit</a>: Framework de desarrollo web
    </p>
""", unsafe_allow_html=True)

# ── Disclaimer ────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>Descargo de Responsabilidad</div>", unsafe_allow_html=True)
st.markdown("""
    <p style='color:#4a6278;font-size:1rem;line-height:1.8'>
    Esta herramienta es exclusivamente para fines de investigación científica. No ha sido aprobada,
    autorizada ni licenciada por ninguna autoridad reguladora. Los datos presentados no deben utilizarse
    como base para diagnóstico clínico, tratamiento de pacientes ni ensayos clínicos en humanos.
    Al utilizar esta plataforma, el usuario reconoce y acepta estas condiciones.
    </p>
""", unsafe_allow_html=True)

render_footer()
