import streamlit as st

from utils import page_header, render_footer, section, setup_page

setup_page("Acerca del Proyecto")

page_header(
    "Acerca del Proyecto",
    """Este dashboard forma parte de un esfuerzo colaborativo de vigilancia genómica de
    <i>Mycobacterium tuberculosis</i> en México, desarrollado en el marco del Centro de Investigación,
    Innovación y Vigilancia Genómica de Enfermedades Infecciosas (CIIViGEI) de la Universidad
    Autónoma de Baja California (UABC), Ensenada, Baja California, México.""",
    sample_size=False,
)


# ── Equipo ──────────────────────────────────────────────────────────
section("Equipo de Trabajo")
st.markdown("""
    <p class='texto' style='line-height:1.9'>
    <b>Dra. Raquel Muñiz-Salazar — Colaboradora Nacional</b><br>
    &nbsp;&nbsp;• Profesora-Investigadora, Escuela de Ciencias de la Salud, UABC<br>
    &nbsp;&nbsp;• Coordinadora de Investigación y Posgrado, ECS-UABC<br>
    &nbsp;&nbsp;• Coordinadora del CIIViGEI, UABC<br>
    &nbsp;&nbsp;• Presidenta de The Union Latinoamérica (2023–2026)<br>
    &nbsp;&nbsp;• Presidenta de RemiTB
    </p>

    <p class='texto' style='line-height:1.9'>
    <b>Dra. Dora-Luz Flores — Colaboradora Nacional</b><br>
    &nbsp;&nbsp;• Coordinadora General de Investigación y Posgrado, UABC <br>
    &nbsp;&nbsp;• Profesora-Investigadora, Facultad de Ingeniería, Arquitectura y Diseño, UABC <br>
    &nbsp;&nbsp;• Vicepresidenta del Consejo Mexicano de Estudios de Posgrado (COMEPO) <br>
    &nbsp;&nbsp;• Miembro del Liaison Committee of the ISC Regional Focal Point for the LACR
    </p>

    <p class='texto' style='line-height:1.9'>
    <b>Dr. Giuseppe Pirrò — Colaborador Internacional</b><br>
    &nbsp;&nbsp;• Profesor Asociado, Ciencias de la Computación, Università della Calabria, Italia<br>
    &nbsp;&nbsp;• Departamento DEMACS (Ingegneria Informatica, Modellistica, Elettronica e Sistemistica)<br>
    &nbsp;&nbsp;• Áreas: Web Semántica, Bases de datos orientadas a grafos, Knowledge Graphs, Sistemas distribuidos
    </p>

    <p class='texto' style='line-height:1.9'>
    <b>Ing. Daniela Santana Camacho — Desarrollo y análisis de datos</b><br>
    &nbsp;&nbsp;• Bioingeniera, Universidad Autónoma de Baja California<br>
    &nbsp;&nbsp;• Estudiante de posgrado en Biotecnología de la Salud, DiBEST, Università della Calabria, Italia
    </p>
""", unsafe_allow_html=True)

# ── Recursos ─────────────────────────────────────────────────────────
section("Recursos utilizados")
st.markdown("""
    <p class='texto' style='line-height:2.2'>
    • <a href='https://www.ncbi.nlm.nih.gov/' target='_blank'>NCBI</a>: Recopilación de muestras y genomas<br>
    • <a href='https://github.com/jodyphelan/TBProfiler' target='_blank'>TB-Profiler</a>: Análisis genómico<br>
    • <a href='https://www.who.int/publications/i/item/9789240082410' target='_blank'>Catálogo de mutaciones de la OMS</a>: Clasificación de mutaciones y farmacorresistencia<br>
    • <a href='https://neo4j.com/' target='_blank'>Neo4j</a>: Base de datos orientada a grafos<br>
    • <a href='https://streamlit.io/' target='_blank'>Streamlit</a>: Framework de desarrollo web
    </p>
""", unsafe_allow_html=True)

# ── Descargo de responsabilidad ──────────────────────────────────────
section("Descargo de Responsabilidad")
st.markdown("""
    <p class='texto' style='line-height:1.8'>
    Esta herramienta es exclusivamente para fines de investigación científica. No ha sido aprobada,
    autorizada ni licenciada por ninguna autoridad reguladora. Los datos presentados no deben utilizarse
    como base para diagnóstico clínico, tratamiento de pacientes ni ensayos clínicos en humanos.
    Al utilizar esta plataforma, el usuario reconoce y acepta estas condiciones.
    </p>
""", unsafe_allow_html=True)

render_footer()
