#Componentes compartidos por todas las páginas de Streamlit
import base64  #convierte png en txt para html
 #consulta API de github
import json 
import os
import urllib.request 
from datetime import datetime
import streamlit as st  #dibuja la página web

GITHUB_REPO = "tuberculosisuabc/tb-mx-vigilancia"  #repositorio para leer fecha de actulización

# Tabs de la página: nombre, ruta 
PAGES = [
    ("Inicio", "/"),
    ("Farmacorresistencia", "/Farmacorresistencia"),
    ("Mapa", "/Mapa"),
    ("Tendencias", "/Tendencias"),
    ("Linajes", "/Linajes"),
    ("Mutaciones", "/Mutaciones"),
    ("Muestras", "/Muestras"),
    ("Base de datos", "/Base_de_datos"),
    ("Acerca del Proyecto", "/Acerca_del_Proyecto"),
]

# Colores de texto
TEXT_MUTED = "#3D5A4D" # párrafos y ejes
TEXT_DARK = "#1B3A2D" # títulos y etiquetas
LINK = "#2D6A4F"
GRID = "#D5D0C4"
BG  = "#F4F1EA"

#Farmacorresistencia
DRTYPE_LABELS = { # Reenombrar etiquetas de perfil de resistencia, drtype de TB-Profiler a nomenclatura español (OMS)
    "Sensitive": "Sensible",
    "HR-TB": "TB-Hr",
    "RR-TB": "TB-RR",
    "MDR-TB": "TB-MDR",
    "Pre-XDR-TB": "TB-pre-XDR",
    "XDR-TB": "TB-XDR",
    "Other": "Otra resistencia",
    "Low_coverage": "Baja cobertura",
    "No-Mtb": "M. bovis / BCG",
}

DRTYPE_COLORS = {  # Colores para resistencia
    "Sensible": "#22c55e",
    "TB-Hr": "#eab308",
    "TB-RR": "#f97316",
    "TB-MDR": "#dc2626",
    "TB-pre-XDR": "#9333ea",
    "TB-XDR": "#1f2937",
    "Otra resistencia": "#94a3b8",
    "Baja cobertura": "#cbd5e1",
    "M. bovis / BCG": "#92400e",
}

DRTYPE_ICONS = { # Íconos para las tablas (mismos colores que DRTYPE_COLORS)
    "Sensible":"🟢",
    "TB-Hr": "🟡",
    "TB-RR": "🟠",
    "TB-MDR": "🔴",
    "TB-pre-XDR": "🟣",
    "TB-XDR": "⚫",
    "Otra resistencia": "⚪",
    "Baja cobertura": "⬜",
    "M. bovis / BCG": "🟤",
}

DRTYPE_DESCRIPTIONS = {   #Definiciones 
    "Sensible": "Sin variantes de resistencia detectadas",
    "TB-Hr": "Resistencia a isoniacida, sin resistencia a rifampicina",
    "TB-RR": "Resistencia a rifampicina",
    "TB-MDR": "Resistencia a rifampicina + isoniacida",
    "TB-pre-XDR": "TB-MDR/RR + fluoroquinolona",
    "TB-XDR": "TB-pre-XDR + bedaquilina y/o linezolid",
    "Otra resistencia": "Resistencia a otros fármacos (sin isoniacida ni rifampicina)",
}


def drtype_es(value):  #Función, traduce drtype
    return DRTYPE_LABELS.get(value, value)


# Linaje
LINEAGE_LABELS = { #nombre del linaje y su etiqueta
    "lineage1": "L1", "lineage2": "L2", "lineage3": "L3", "lineage4": "L4", 
    "lineage7": "L7", "lineage8": "L8", "mixed": "Mixta",
}

LINEAGE_DESCRIPTIONS = {  #descripción de cada linaje
    "L1": "Indo-Oceánico",
    "L2": "Asia oriental / Beijing",
    "L3": "África oriental e India",
    "L4": "Europa, América, África",
    "L7": "Etíope",
    "L8": "Grandes Lagos de África ",
    "Mixta": "Infección mixta (más de un linaje detectado)",
}

LINEAGE_COLORS = { #Asigna color a cada linaje
    "L1": "#7c3aed",
    "L2": "#2563eb",
    "L3": "#0891b2",
    "L4": "#2D6A4F",
    "L7": "#db2777",
    "Mixta": "#94a3b8",
}


def lineage_es(value): #función para convertir etiquetas de lianhes
    if not isinstance(value, str) or not value:
        return value
    if ";" in value: #si se detectan mas de un linaje se clasifica como mixta
        return "Mixta"
    return LINEAGE_LABELS.get(value.split(".")[0], value)


def sublineage_es(value): #función para eliminar la palabara "lineage" y mostrar sublinaje
    if not isinstance(value, str):
        return value
    return value.replace("lineage", "")


# Fármacos
DRUG_NAMES = {  #Nombres de fármacos a español, vienen de TB-Profiler en inglées
    "isoniazid": "Isoniacida",
    "rifampicin": "Rifampicina",
    "ethambutol": "Etambutol",
    "pyrazinamide": "Pirazinamida",
    "streptomycin": "Estreptomicina",
    "levofloxacin": "Levofloxacino",
    "moxifloxacin": "Moxifloxacino",
    "bedaquiline":  "Bedaquilina",
    "linezolid": "Linezolid",
    "clofazimine": "Clofazimina",
    "delamanid": "Delamanid",
    "pretomanid":  "Pretomanid",
    "amikacin": "Amikacina",
    "kanamycin": "Kanamicina",
    "capreomycin": "Capreomicina",
    "ethionamide": "Etionamida",
    "prothionamide": "Protionamida",
    "para-aminosalicylic_acid": "Ácido p-aminosalicílico",
    "cycloserine": "Cicloserina",
}

DRUG_COLORS = { #color para cada fármaco
    "isoniazid":  "#f87171",
    "rifampicin": "#fb923c",
    "ethambutol": "#fbbf24",
    "pyrazinamide": "#a3e635",
    "streptomycin": "#34d399",
    "moxifloxacin": "#22d3ee",
    "levofloxacin":"#60a5fa",
    "bedaquiline":"#a78bfa",
    "linezolid":"#e879f9",
    "amikacin": "#f472b6",
    "kanamycin": "#fb7185",
    "capreomycin": "#c084fc",
    "ethionamide": "#86efac",
    "clofazimine": "#7dd3fc",
    "delamanid":  "#fda4af",
    "para-aminosalicylic_acid": "#fcd34d",
}
MULTI_DRUG_COLOR = "#94a3b8" # mutaciones asociadas a más de un fármaco

def drug_es(value): #Función para traducir el nombre del fármaco
    return DRUG_NAMES.get(value, value)

DRUG_CLASS_LABELS = { # Grupos por clasificación de la OMS 2022 (se establece en pipeline/03_build_graph_csvs.py)
    "first_line": "Primera línea",
    "group_A": "Grupo A",
    "group_B": "Grupo B",
    "group_C": "Grupo C",
    "not_recommended": "No recomendados",
    "bpal_regimen": "Régimen BPaL",
    "other": "Otros",
}

DRUG_CLASS_COLORS = { #Colores para grupos
    "first_line": "#f87171",
    "group_A": "#e879f9",
    "group_B":"#a78bfa",
    "group_C":  "#60a5fa",
    "not_recommended": "#94a3b8",
    "bpal_regimen": "#f59e0b",
    "other": "#64748b",
}

CONFIDENCE_LABELS = { # Valor de confianza de las mutaciones (TB-Profiler basado en catálogo de la OMS)
    "Assoc w R": "Asociada a resistencia",
    "Assoc w R - Interim": "Asociada a resistencia (provisional)",
    "Uncertain significance": "Significado incierto",
    "": "Sin clasificar (literatura)",
}

def confidence_es(value): #Función para traducir nivel de confianza de la mutación
    return CONFIDENCE_LABELS.get(value, value)


# Estilo de la página, se inserta en cada pestaña
#!important para sobreponerse a los estilos de Streamlit y personalizar
SHARED_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap'); /*tipo de letra*/

html, body, [class*="css"], p, span, div, label, button, input {
    font-family: 'Poppins', sans-serif !important;
}

/* Ocultar el menú lateral y elementos de Streamlit */
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
[data-testid="stHeader"] { display: none !important; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* Fondo de la aplicación */
.stApp { background: #F4F1EA; }

/* Contenedor principal */
.block-container {
    padding-top: 0 !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
    max-width: 100% !important;
    padding-bottom: 3rem !important;
}

/* Encabezado: logo + título*/
.site-header {
    background: #EDECE4;
    width: 100vw;
    margin-left: calc(50% - 50vw);
    padding: 16px 2rem 14px;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 18px;
    border-bottom: 1px solid #D5D0C4;
}
.site-header-text { display: flex; flex-direction: column; gap: 3px; }
.site-header-title {
    font-family: 'Poppins', sans-serif;
    font-size: 1.1rem;
    font-weight: 600;
    color: #1B3A2D;
    line-height: 1.2;
    margin: 0;
}
.site-header-sub {
    font-family: 'Poppins', sans-serif;
    font-size: 0.7rem;
    font-weight: 400;
    color: #5C7A6B;
    letter-spacing: 0.03em;
    margin: 0;
}

/* Barra de navegación (pestañas) */
.topnav {
    background: #1B3A2D;
    width: 100vw;
    margin-left: calc(50% - 50vw);
    margin-bottom: 1.8rem;
    padding: 0 1.5rem;
    box-sizing: border-box;
    display: flex;
    align-items: stretch;
    overflow-x: auto;
    scrollbar-width: none;
    -ms-overflow-style: none;
}
.topnav::-webkit-scrollbar { display: none; }

.topnav a {
    font-family: 'Poppins', sans-serif !important;
    font-size: 14px !important;
    font-weight: 400 !important;
    color: #8DC4A8 !important;
    padding: 14px 18px !important;
    white-space: nowrap !important;
    text-decoration: none !important;
    border-bottom: 3px solid transparent !important;
    display: block !important;
    letter-spacing: 0.01em !important;
    transition: color 0.15s, border-color 0.15s !important;
}
.topnav a:hover {
    color: #D4EDE0 !important;
    border-bottom-color: #52B788 !important;
}
.topnav a.active {
    color: #FFFFFF !important;
    font-weight: 500 !important;
    border-bottom: 3px solid #52B788 !important;
}

/* Títulos de cada sección*/
.section-header {
    font-family: 'Poppins', sans-serif;
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #3D5A4D;
    margin: 30px 0 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #C8C4BC;
}

/* Tarjetas KPI  de resumen */
.kpi-card {
    background: #FFFFFF;
    border-radius: 10px;
    padding: clamp(10px, 1.2vw, 18px) clamp(8px, 1vw, 16px);
    text-align: center;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.kpi-card.kpi-green { border-bottom: 3px solid #2D6A4F; }
.kpi-card.kpi-amber { border-bottom: 3px solid #C68A00; }
.kpi-card.kpi-red   { border-bottom: 3px solid #C44B2B; }
.kpi-card.kpi-plain { border-bottom: 3px solid #B0A898; }

.kpi-value {
    font-family: 'Poppins', sans-serif;
    font-size: clamp(1.2rem, 2vw, 2.2rem);
    font-weight: 600;
    line-height: 1;
    margin-bottom: 5px;
    word-break: break-word;
}
.kpi-card.kpi-green .kpi-value { color: #2D6A4F; }
.kpi-card.kpi-amber .kpi-value { color: #9A6800; }
.kpi-card.kpi-red   .kpi-value { color: #C44B2B; }
.kpi-card.kpi-plain .kpi-value { color: #1B3A2D; }

.kpi-label {
    font-family: 'Poppins', sans-serif;
    font-size: clamp(0.48rem, 0.6vw, 0.68rem);
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #7A9A8A;
    word-break: break-word;
}

/* Tarjetas de estadísticas (Pestaña: Base de datos) */
.stat-card {
    background: #FFFFFF;
    border-radius: 10px;
    padding: clamp(10px, 1.2vw, 18px) clamp(8px, 1vw, 20px);
    text-align: center;
    border-bottom: 3px solid #2D6A4F;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.stat-number {
    font-family: 'Poppins', sans-serif;
    font-size: clamp(1.2rem, 1.8vw, 2rem);
    font-weight: 600;
    color: #2D6A4F;
    line-height: 1;
}
.stat-label {
    font-family: 'Poppins', sans-serif;
    font-size: clamp(0.48rem, 0.6vw, 0.68rem);
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #7A9A8A;
    margin-top: 5px;
}

/* Títulos  */
h1 {
    font-family: 'Poppins', sans-serif !important;
    color: #1B3A2D !important;
    font-size: 1.9rem !important;
    font-weight: 600 !important;
    margin-bottom: 4px !important;
    line-height: 1.2 !important;
}
h2, h3 {
    font-family: 'Poppins', sans-serif !important;
    color: #1B3A2D !important;
}

/* Texto de las páginas */
.texto-intro { color: #3D5A4D !important; font-size: 1.05rem !important; line-height: 1.7 !important; }
.texto       { color: #3D5A4D !important; font-size: 1rem !important; line-height: 1.7; }
.texto-nota  { color: #5C7A6B !important; font-size: 0.78rem !important; line-height: 1.9 !important; padding: 0 8px; }
.texto-intro a, .texto a, .texto-nota a { color: #2D6A4F; text-decoration: underline; }

/* Pie de página  */
.site-footer {
    background: #1B3A2D;
    width: 100vw;
    margin-left: calc(50% - 50vw);
    margin-top: 2.5rem;
    padding: 11px 2rem;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    gap: 2.5rem;
    flex-wrap: wrap;
}
.site-footer span   { font-family: 'Poppins', sans-serif; font-size: 0.75rem; color: #8DC4A8; }
.site-footer strong { color: #D4EDE0; font-weight: 500; }

/* Cuadro de tamaño de muestra  */
.sample-size {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #EAF3ED;
    border: 1px solid #B2D4BF;
    border-radius: 6px;
    padding: 5px 12px;
    margin-top: 16px;
    margin-bottom: 8px;
}
.sample-size span   { font-family: 'Poppins', sans-serif; font-size: 0.78rem; color: #3D5A4D; }
.sample-size strong { color: #1B3A2D; }
</style>"""


# ESTRUCTURA DE LAS PÁGINAS
def _logo_img_tag(height: int = 52) -> str:
    logo_path = os.path.join(os.path.dirname(__file__), "SVG-TB-MX.png")  #decodificar para insertar logo
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return (f'<img src="data:image/png;base64,{b64}" height="{height}" '
                'style="object-fit:contain;" alt="SVG-TB-MX">')
    return '<span style="font-size:1.8rem;">🫁</span>'


def setup_page(active: str): #configura la página, establece estilos, encabezado
    st.set_page_config(
        page_title="SVG-TB-MX" if active == "Inicio" else f"{active} · SVG-TB-MX",
        page_icon="🫁",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(SHARED_CSS, unsafe_allow_html=True) #inserta estilos
    st.markdown(f"""
    <div class="site-header"> #encabezado
        {_logo_img_tag(52)}
        <div class="site-header-text">
            <p class="site-header-title">
                Sistema de Vigilancia Genómica para Tuberculosis en México
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    items = "".join(
        f'<a href="{url}" target="_self" class="{"active" if label == active else ""}">{label}</a>'
        for label, url in PAGES
    )
    st.markdown(f'<nav class="topnav">{items}</nav>', unsafe_allow_html=True)


def page_header(title: str, intro_html: str, sample_size: bool = True): #título de pagina y descripción
    st.markdown(f"<h1>{title}</h1><p class='texto-intro'>{intro_html}</p>",
                unsafe_allow_html=True)
    if sample_size:  #cuadro de tamaño de muestra
        render_sample_size()


def section(title: str, text_html: str = ""): #título de la sección y descripción, si hay
    """Título de sección y, si se indica, un párrafo explicativo."""
    st.markdown(f"<div class='section-header'>{title}</div>", unsafe_allow_html=True)
    if text_html:
        st.markdown(f"<p class='texto'>{text_html}</p>", unsafe_allow_html=True)


def render_sample_size(): #Indicador con el número de genomas con QC aprobado
    from db import get_kpis  #consulta en neo4j
    try:
        qc_pass = get_kpis().get("qc_pass", "—")
    except Exception:
        qc_pass = "—"
    st.markdown(f"<div class='sample-size'><span>🧬 Tamaño de muestra: "
                f"<strong>{qc_pass} genomas</strong></span></div>", unsafe_allow_html=True)


@st.cache_data(ttl=3600)
def get_last_pipeline_run() -> str: #toma fecha de la última actualizacióm
    meses = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    try:
        url = (f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/"
               "pipeline.yml/runs?status=success&per_page=1")  #accede al repositorio para ver última corrida
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            runs = json.load(resp).get("workflow_runs", [])
        if not runs:
            return ""
        last = datetime.strptime(runs[0]["updated_at"][:10], "%Y-%m-%d") #llega todo el nombre del archivo, se usan primeros 10 caracteres para fecha
        return f"{meses[last.month]} {last.year}"
    except Exception:
        return ""


def render_footer(): #Pie de página
    fecha = get_last_pipeline_run()
    partes = [("Datos", "NCBI SRA"), ("Análisis", "TB-Profiler v6"), ("Base", "Neo4j")]
    if fecha:
        partes.append(("Datos actualizados", fecha))
    spans = "".join(f"<span>{k}: <strong>{v}</strong></span>" for k, v in partes)
    st.markdown(f"<div class='site-footer'>{spans}</div>", unsafe_allow_html=True)

# GRÁFICAS  
#Ejes con y sin cuadrícula
AXIS_GRID  = dict(showgrid=True, gridcolor=GRID, color=TEXT_MUTED) #
AXIS_PLAIN = dict(showgrid=False, color=TEXT_MUTED) 

def style_fig(fig, height: int, margin: dict = None, legend: dict = None, **layout): #establece estilo de figura
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT_MUTED, family="Poppins"),
        margin=margin or dict(t=10, b=10, l=10, r=10),
        height=height,
        **layout,
    )
    if legend is not None:
        fig.update_layout(legend={"bgcolor": "rgba(0,0,0,0)", "font": {"size": 11}, **legend})
    return fig


def show_fig(fig): #figura se ajusta al espacio disponible, ancho
    st.plotly_chart(fig, use_container_width=True)
