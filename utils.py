"""
Componentes compartidos por todas las páginas del sitio: estilos, encabezado,
barra de navegación, pie de página, funciones para configurar páginas y
gráficas, y los colores y etiquetas en español de cada categoría.
"""
import base64
import json
import os
import urllib.request
from datetime import datetime

import streamlit as st

GITHUB_REPO = "tuberculosisuabc/tb-mx-vigilancia"

# Páginas de la barra de navegación: (nombre, ruta)
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


# ══════════════════════════════════════════════════════════════════════
# COLORES Y ETIQUETAS
# La base de datos guarda los valores en inglés (los genera el pipeline de la
# tesis); aquí se define una sola vez cómo se muestran en el sitio: el color de
# cada categoría y su nombre en español, igual en todas las gráficas y tablas.
# ══════════════════════════════════════════════════════════════════════

# ── Colores de texto del sitio ───────────────────────────────────────
TEXT_MUTED = "#3D5A4D"     # párrafos y ejes
TEXT_DARK  = "#1B3A2D"     # títulos y etiquetas
LINK       = "#2D6A4F"
GRID       = "#D5D0C4"
BG         = "#F4F1EA"


# ── Perfil de resistencia (drtype de TB-Profiler) ───────────────────
# Nomenclatura en español usada por la OMS/OPS: TB-RR, TB-MDR, TB-XDR...
DRTYPE_LABELS = {
    "Sensitive":    "Sensible",
    "HR-TB":        "TB-Hr",
    "RR-TB":        "TB-RR",
    "MDR-TB":       "TB-MDR",
    "Pre-XDR-TB":   "TB-pre-XDR",
    "XDR-TB":       "TB-XDR",
    "Other":        "Otra resistencia",
    "Low_coverage": "Baja cobertura",
    "No-Mtb":       "M. bovis / BCG",
}
# Colores ordenados de menor a mayor resistencia; coinciden con los íconos
DRTYPE_COLORS = {
    "Sensible":         "#22c55e",
    "TB-Hr":            "#eab308",
    "TB-RR":            "#f97316",
    "TB-MDR":           "#dc2626",
    "TB-pre-XDR":       "#9333ea",
    "TB-XDR":           "#1f2937",
    "Otra resistencia": "#94a3b8",
    "Baja cobertura":   "#cbd5e1",
    "M. bovis / BCG":   "#92400e",
}
# Íconos para las tablas (los mismos colores que DRTYPE_COLORS)
DRTYPE_ICONS = {
    "Sensible":         "🟢",
    "TB-Hr":            "🟡",
    "TB-RR":            "🟠",
    "TB-MDR":           "🔴",
    "TB-pre-XDR":       "🟣",
    "TB-XDR":           "⚫",
    "Otra resistencia": "⚪",
    "Baja cobertura":   "⬜",
    "M. bovis / BCG":   "🟤",
}
DRTYPE_DESCRIPTIONS = {
    "Sensible":         "Sin variantes de resistencia detectadas",
    "TB-Hr":            "Resistencia a isoniacida, sin resistencia a rifampicina",
    "TB-RR":            "Resistencia a rifampicina",
    "TB-MDR":           "Resistencia a rifampicina <b>+</b> isoniacida",
    "TB-pre-XDR":       "TB-MDR/RR <b>+</b> fluoroquinolona",
    "TB-XDR":           "TB-pre-XDR <b>+</b> bedaquilina y/o linezolid",
    "Otra resistencia": "Resistencia a otros fármacos (sin isoniacida ni rifampicina)",
    "M. bovis / BCG":   "Complejo <i>M. tuberculosis</i>, pero no <i>M. tuberculosis</i>",
}


def drtype_es(value):
    return DRTYPE_LABELS.get(value, value)


# ── Linajes ─────────────────────────────────────────────────────────
LINEAGE_LABELS = {
    "lineage1": "L1", "lineage2": "L2", "lineage3": "L3", "lineage4": "L4",
    "lineage5": "L5", "lineage6": "L6", "lineage7": "L7", "lineage8": "L8",
    "lineage9": "L9", "La1": "La1", "La2": "La2", "La3": "La3", "mixed": "Mixta",
}
LINEAGE_DESCRIPTIONS = {
    "L1":    "Indo-Oceánico",
    "L2":    "Asiático oriental / Beijing",
    "L3":    "Africano oriental-Indio",
    "L4":    "Euroamericano",
    "L5":    "Africano occidental 1 (M. africanum)",
    "L6":    "Africano occidental 2 (M. africanum)",
    "L7":    "Etíope",
    "L8":    "Linaje 8",
    "L9":    "Linaje 9",
    "La1":   "M. bovis (incluye BCG)",
    "La2":   "M. caprae",
    "La3":   "M. orygis",
    "Mixta": "Infección mixta (más de un linaje detectado)",
}
LINEAGE_COLORS = {
    "L1":    "#7c3aed",
    "L2":    "#2563eb",
    "L3":    "#0891b2",
    "L4":    "#2D6A4F",
    "L5":    "#ca8a04",
    "L6":    "#ea580c",
    "L7":    "#db2777",
    "La1":   "#92400e",
    "La2":   "#b45309",
    "La3":   "#78716c",
    "Mixta": "#94a3b8",
}


def lineage_es(value):
    """'lineage4' -> 'L4'; 'lineage2;lineage4' -> 'Mixta'."""
    if not isinstance(value, str) or not value:
        return value
    if ";" in value:
        return "Mixta"
    return LINEAGE_LABELS.get(value.split(".")[0], value)


def sublineage_es(value):
    """'lineage4.1.2' -> '4.1.2'; 'La1.8.1' se deja igual."""
    if not isinstance(value, str):
        return value
    return value.replace("lineage", "")


# ── Fármacos ────────────────────────────────────────────────────────
DRUG_NAMES = {
    "isoniazid":                "Isoniacida",
    "rifampicin":               "Rifampicina",
    "ethambutol":               "Etambutol",
    "pyrazinamide":             "Pirazinamida",
    "streptomycin":             "Estreptomicina",
    "levofloxacin":             "Levofloxacino",
    "moxifloxacin":             "Moxifloxacino",
    "bedaquiline":              "Bedaquilina",
    "linezolid":                "Linezolid",
    "clofazimine":              "Clofazimina",
    "delamanid":                "Delamanid",
    "pretomanid":               "Pretomanid",
    "amikacin":                 "Amikacina",
    "kanamycin":                "Kanamicina",
    "capreomycin":              "Capreomicina",
    "ethionamide":              "Etionamida",
    "prothionamide":            "Protionamida",
    "para-aminosalicylic_acid": "Ácido p-aminosalicílico",
    "cycloserine":              "Cicloserina",
}
DRUG_COLORS = {
    "isoniazid":                "#f87171",
    "rifampicin":               "#fb923c",
    "ethambutol":               "#fbbf24",
    "pyrazinamide":             "#a3e635",
    "streptomycin":             "#34d399",
    "moxifloxacin":             "#22d3ee",
    "levofloxacin":             "#60a5fa",
    "bedaquiline":              "#a78bfa",
    "linezolid":                "#e879f9",
    "amikacin":                 "#f472b6",
    "kanamycin":                "#fb7185",
    "capreomycin":              "#c084fc",
    "ethionamide":              "#86efac",
    "clofazimine":              "#7dd3fc",
    "delamanid":                "#fda4af",
    "para-aminosalicylic_acid": "#fcd34d",
}
MULTI_DRUG_COLOR = "#94a3b8"   # mutaciones asociadas a más de un fármaco


def drug_es(value):
    return DRUG_NAMES.get(value, value)


# Clasificación de la OMS 2022 (la asigna pipeline/03_build_graph_csvs.py)
DRUG_CLASS_LABELS = {
    "first_line":      "Primera línea",
    "group_A":         "Grupo A",
    "group_B":         "Grupo B",
    "group_C":         "Grupo C",
    "not_recommended": "Ya no recomendados",
    "bpal_regimen":    "Régimen BPaL",
    "other":           "Otros",
}
DRUG_CLASS_COLORS = {
    "first_line":      "#f87171",
    "group_A":         "#e879f9",
    "group_B":         "#a78bfa",
    "group_C":         "#60a5fa",
    "not_recommended": "#94a3b8",
    "bpal_regimen":    "#f59e0b",
    "other":           "#64748b",
}


# ── Confianza de las mutaciones (TB-Profiler / catálogo de la OMS) ───
CONFIDENCE_LABELS = {
    "Assoc w R":              "Asociada a resistencia",
    "Assoc w R - Interim":    "Asociada a resistencia (provisional)",
    "Uncertain significance": "Significado incierto",
    "":                       "Sin clasificar (literatura)",
}


def confidence_es(value):
    return CONFIDENCE_LABELS.get(value, value)


# ══════════════════════════════════════════════════════════════════════
# ESTILOS
# ══════════════════════════════════════════════════════════════════════
SHARED_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap');

html, body, [class*="css"], p, span, div, label, button, input {
    font-family: 'Poppins', sans-serif !important;
}

/* Ocultar el menú lateral y los elementos propios de Streamlit */
[data-testid="stSidebar"]        { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
[data-testid="stHeader"]         { display: none !important; }
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }

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

/* ── Encabezado del sitio (logo + título) ─────────────────────────── */
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

/* ── Barra de navegación ──────────────────────────────────────────── */
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

/* ── Títulos de sección ───────────────────────────────────────────── */
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

/* ── Tarjetas KPI ─────────────────────────────────────────────────── */
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

/* ── Tarjetas de estadísticas (Base de datos) ─────────────────────── */
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

/* ── Títulos ──────────────────────────────────────────────────────── */
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

/* ── Texto de las páginas ─────────────────────────────────────────── */
/* !important: los estilos propios de Streamlit para <p> tienen prioridad sobre una clase */
.texto-intro { color: #3D5A4D !important; font-size: 1.05rem !important; line-height: 1.7 !important; }
.texto       { color: #3D5A4D !important; font-size: 1rem !important; line-height: 1.7; }
.texto-nota  { color: #5C7A6B !important; font-size: 0.78rem !important; line-height: 1.9 !important; padding: 0 8px; }
.texto-intro a, .texto a, .texto-nota a { color: #2D6A4F; text-decoration: underline; }

/* ── Pie de página ────────────────────────────────────────────────── */
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

/* ── Indicador de tamaño de muestra ───────────────────────────────── */
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


# ══════════════════════════════════════════════════════════════════════
# ESTRUCTURA DE LAS PÁGINAS
# ══════════════════════════════════════════════════════════════════════
def _logo_img_tag(height: int = 52) -> str:
    """Logo embebido en base64 (o un emoji si no se encuentra el archivo)."""
    logo_path = os.path.join(os.path.dirname(__file__), "SVG-TB-MX.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        return (f'<img src="data:image/png;base64,{b64}" height="{height}" '
                'style="object-fit:contain;" alt="SVG-TB-MX">')
    return '<span style="font-size:1.8rem;">🫁</span>'


def setup_page(active: str):
    """Configura la página y dibuja estilos, encabezado del sitio y navegación.
    Debe ser lo primero que se llama en cada página."""
    st.set_page_config(
        page_title="SVG-TB-MX" if active == "Inicio" else f"{active} · SVG-TB-MX",
        page_icon="🫁",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(SHARED_CSS, unsafe_allow_html=True)
    st.markdown(f"""
    <div class="site-header">
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


def page_header(title: str, intro_html: str, sample_size: bool = True):
    """Título de la página, texto introductorio y (opcional) el tamaño de muestra."""
    st.markdown(f"<h1>{title}</h1><p class='texto-intro'>{intro_html}</p>",
                unsafe_allow_html=True)
    if sample_size:
        render_sample_size()


def section(title: str, text_html: str = ""):
    """Título de sección y, si se indica, un párrafo explicativo."""
    st.markdown(f"<div class='section-header'>{title}</div>", unsafe_allow_html=True)
    if text_html:
        st.markdown(f"<p class='texto'>{text_html}</p>", unsafe_allow_html=True)


def render_sample_size():
    """Indicador con el número de genomas con QC aprobado."""
    from db import get_kpis
    try:
        qc_pass = get_kpis().get("qc_pass", "—")
    except Exception:
        qc_pass = "—"
    st.markdown(f"<div class='sample-size'><span>🧬 Tamaño de muestra: "
                f"<strong>{qc_pass} genomas</strong></span></div>", unsafe_allow_html=True)


@st.cache_data(ttl=3600)
def get_last_pipeline_run() -> str:
    """Fecha de la última ejecución exitosa del workflow "Actualizar pipeline TB-MX"
    (.github/workflows/pipeline.yml), p. ej. '16 de octubre de 2026'.
    Devuelve '' si no se puede consultar GitHub (el pie de página omite la fecha)."""
    meses = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    try:
        url = (f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/"
               "pipeline.yml/runs?status=success&per_page=1")
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            runs = json.load(resp).get("workflow_runs", [])
        if not runs:
            return ""
        last = datetime.strptime(runs[0]["updated_at"][:10], "%Y-%m-%d")
        return f"{meses[last.month]} {last.year}"
    except Exception:
        return ""


def render_footer():
    """Barra inferior con las fuentes de datos y la fecha de la última actualización."""
    fecha = get_last_pipeline_run()
    partes = [("Datos", "NCBI SRA"), ("Análisis", "TB-Profiler v6"), ("Base", "Neo4j")]
    if fecha:
        partes.append(("Datos actualizados", fecha))
    # Todo en una sola línea: en Markdown, una línea en blanco seguida de texto
    # con sangría se mostraría como bloque de código en vez de HTML
    spans = "".join(f"<span>{k}: <strong>{v}</strong></span>" for k, v in partes)
    st.markdown(f"<div class='site-footer'>{spans}</div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
# GRÁFICAS
# ══════════════════════════════════════════════════════════════════════
# Ejes con y sin cuadrícula, para pasar a style_fig(xaxis=..., yaxis=...)
AXIS_GRID  = dict(showgrid=True, gridcolor=GRID, color=TEXT_MUTED)
AXIS_PLAIN = dict(showgrid=False, color=TEXT_MUTED)


def style_fig(fig, height: int, margin: dict = None, legend: dict = None, **layout):
    """Aplica el estilo común del sitio a una figura de Plotly: fondo transparente,
    fuente Poppins, colores de texto y leyenda sin fondo."""
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


def show_fig(fig):
    st.plotly_chart(fig, use_container_width=True)
