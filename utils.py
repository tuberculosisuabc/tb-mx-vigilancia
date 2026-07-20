import streamlit as st
import base64
import os
from datetime import datetime

# LOGO — loaded from file and embedded as base64

def _get_logo_b64() -> str:
    logo_path = os.path.join(os.path.dirname(__file__), "SVG-TB-MX.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""


def _logo_img_tag(height: int = 52) -> str:
    b64 = _get_logo_b64()
    if b64:
        return f'<img src="data:image/png;base64,{b64}" height="{height}" style="object-fit:contain;" alt="SVG-TB-MX">'
    return '<span style="font-size:1.8rem;">🫁</span>'

# SHARED COMPONENTS
SHARED_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap');

html, body, [class*="css"], p, span, div, label, button, input {
    font-family: 'Poppins', sans-serif !important;
}

/* Hide sidebar & Streamlit chrome */
[data-testid="stSidebar"]        { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
[data-testid="stHeader"]         { display: none !important; }
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }

/* App background */
.stApp { background: #F4F1EA; }

/* Block container */
.block-container {
    padding-top: 0 !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
    max-width: 100% !important;
    padding-bottom: 3rem !important;
}

/* ── Site header (logo + title) ───────────────────────────────────── */
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

/* ── Top navigation bar ───────────────────────────────────────────── */
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

/* ── Section headers ─────────────────────────────────────────────── */
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

/* ── KPI cards ───────────────────────────────────────────────────── */
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

/* ── Stat cards (Base de datos) ──────────────────────────────────── */
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

/* ── Headings ─────────────────────────────────────────────────────── */
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
</style>"""

# ── Page registry ─────────────────────────────────────────────────────
_PAGES = [
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


def render_topnav(current_page: str = "Inicio"):
    """Render shared CSS, site header with logo, and top navigation bar."""
    st.markdown(SHARED_CSS, unsafe_allow_html=True)

    # ── Site header: logo + title ─────────────────────────────────────
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

    # ── Navigation bar ────────────────────────────────────────────────
    items = "".join(
        f'<a href="{url}" target="_self" class="{"active" if label == current_page else ""}">{label}</a>'
        for label, url in _PAGES
    )
    st.markdown(f'<nav class="topnav">{items}</nav>', unsafe_allow_html=True)


def render_footer():
    """Dark green footer bar — matches nav bar style."""
    meses = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    now = datetime.now()
    fecha = f"{meses[now.month]} {now.year}"
    st.markdown(f"""
    <div style="
        background:#1B3A2D;
        width:100vw;
        margin-left:calc(50% - 50vw);
        margin-top:2.5rem;
        padding:11px 2rem;
        box-sizing:border-box;
        display:flex;
        align-items:center;
        gap:2.5rem;
        flex-wrap:wrap;
    ">
        <span style="font-family:'Poppins',sans-serif;font-size:0.75rem;color:#8DC4A8;">
            Datos: <strong style="color:#D4EDE0;font-weight:500;">NCBI SRA</strong>
        </span>
        <span style="font-family:'Poppins',sans-serif;font-size:0.75rem;color:#8DC4A8;">
            Análisis: <strong style="color:#D4EDE0;font-weight:500;">TB-Profiler v6</strong>
        </span>
        <span style="font-family:'Poppins',sans-serif;font-size:0.75rem;color:#8DC4A8;">
            Base: <strong style="color:#D4EDE0;font-weight:500;">Neo4j</strong>
        </span>
        <span style="font-family:'Poppins',sans-serif;font-size:0.75rem;color:#8DC4A8;">
            Actualizado: <strong style="color:#D4EDE0;font-weight:500;">{fecha}</strong>
        </span>
    </div>
    """, unsafe_allow_html=True)


def render_sample_size():
    """Display a subtle 'Tamaño de muestra' badge using the QC-pass count.
    Call this once per page, right after render_topnav() and the page header."""
    from db import get_kpis
    try:
        kpis = get_kpis()
        qc_pass = kpis.get("qc_pass", "—")
    except Exception:
        qc_pass = "—"
    st.markdown(f"""
    <div style="
        display:inline-flex;
        align-items:center;
        gap:6px;
        background:#EAF3ED;
        border:1px solid #B2D4BF;
        border-radius:6px;
        padding:5px 12px;
        margin-top:16px;
        margin-bottom:8px;
    ">
        <span style="font-family:'Poppins',sans-serif;font-size:0.78rem;color:#3D5A4D;">
            🧬 Tamaño de muestra:
            <strong style="color:#1B3A2D;">{qc_pass} genomas</strong>
        </span>
    </div>
    """, unsafe_allow_html=True)
