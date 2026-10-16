import streamlit as st
import plotly.express as px
import pandas as pd
from db import get_samples_table, get_states, get_drtypes, get_years
from utils import render_topnav, render_footer, render_sample_size
from utils import (DRTYPE_COLORS, DRTYPE_ICONS, DRTYPE_LABELS, LINEAGE_COLORS, drtype_es,
                   drug_es, lineage_es, sublineage_es)

st.set_page_config(
    page_title="Muestras · SVG-TB-MX",
    page_icon="🫁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_topnav("Muestras")

# ── Header ────────────────────────────────────────────────────────────
st.markdown("""
    <h1>Explorador de Muestras</h1>
    <p style='color:#3D5A4D;font-size:1.05rem;line-height:1.7'>
        Filtra y explora los aislamientos secuenciados.
    </p>
""", unsafe_allow_html=True)

render_sample_size()

# ── Filters ───────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>Filtros</div>", unsafe_allow_html=True)

f1, f2, f3, f4 = st.columns(4)

with f1:
    states    = get_states()
    state_sel = st.selectbox("Estado", states)
with f2:
    # Ordenados de menor a mayor resistencia (orden de DRTYPE_LABELS en theme.py)
    orden      = list(DRTYPE_LABELS)
    drtypes    = sorted(get_drtypes(), key=lambda d: orden.index(d) if d in orden else len(orden))
    drtype_sel = st.multiselect("Perfil de resistencia", drtypes, default=drtypes,
                                format_func=drtype_es)
with f3:
    years    = get_years()
    year_sel = st.selectbox("Año de colección", ["Todos"] + [str(y) for y in years])
with f4:
    qc_only = st.checkbox("Solo genomas con QC aprobado", value=True)

# ── Data ──────────────────────────────────────────────────────────────
with st.spinner("Cargando muestras..."):
    rows = get_samples_table(
        drtype_filter=drtype_sel if drtype_sel else None,
        state_filter=state_sel,
        year_filter=int(year_sel) if year_sel != "Todos" else None,
        qc_only=qc_only,
    )

df = pd.DataFrame(rows)
st.markdown(f"<div class='section-header'>{len(df)} muestras encontradas</div>", unsafe_allow_html=True)

if df.empty:
    st.warning("No hay muestras con los filtros seleccionados.")
    st.stop()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total",   len(df))
k2.metric("TB-MDR",  int((df["is_mdr"] == "Yes").sum()))
k3.metric("TB-XDR",  int((df["is_xdr"] == "Yes").sum()))
k4.metric("Estados", df.loc[df["state"].fillna("") != "", "state"].nunique())

# Valores de la base (en inglés) a etiquetas en español (theme.py)
df["drtype"]          = df["drtype"].map(drtype_es)
df["lineage"]         = df["lineage"].map(lineage_es)
df["sub_lineage"]     = df["sub_lineage"].map(sublineage_es)
df["resistant_drugs"] = df["resistant_drugs"].fillna("").apply(
    lambda d: ", ".join(drug_es(x.strip()) for x in d.split(";") if x.strip()))
df["year"] = pd.to_numeric(df["year"], errors="coerce").map(
    lambda y: str(int(y)) if pd.notna(y) else "—")   # año desconocido o rango de fechas
df["state"] = df["state"].fillna("").replace("", "—")
df["drtype_icon"] = df["drtype"].map(DRTYPE_ICONS).fillna("⚪") + " " + df["drtype"].fillna("")

display_cols = {
    "sample_id":       "ID Muestra",
    "drtype_icon":     "Resistencia",
    "lineage":         "Linaje",
    "sub_lineage":     "Sub-linaje",
    "state":           "Estado",
    "year":            "Año",
    "median_depth":    "Profundidad",
    "resistant_drugs": "Fármacos resist.",
}
df_display = df[list(display_cols.keys())].rename(columns=display_cols)

st.dataframe(
    df_display,
    use_container_width=True,
    hide_index=True,
    height=480,
    column_config={
        "ID Muestra":      st.column_config.TextColumn(width="small"),
        "Resistencia":     st.column_config.TextColumn(width="medium"),
        "Año":             st.column_config.TextColumn(width="small"),
        "Profundidad":     st.column_config.NumberColumn(format="%.1f×", width="small"),
        "Fármacos resist.": st.column_config.TextColumn(width="large"),
    }
)

# ── Charts ────────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>Distribución en Selección Actual</div>", unsafe_allow_html=True)

ch1, ch2 = st.columns(2)

with ch1:
    if "drtype" in df.columns:
        drtype_counts = df["drtype"].value_counts().reset_index()
        drtype_counts.columns = ["drtype", "count"]
        fig1 = px.bar(
            drtype_counts, x="count", y="drtype", orientation="h",
            color="drtype",
            color_discrete_map=DRTYPE_COLORS,
            labels={"count": "Muestras", "drtype": ""},
        )
        fig1.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#3D5A4D", family="Poppins"),
            showlegend=False,
            xaxis=dict(showgrid=True, gridcolor="#D5D0C4", color="#3D5A4D"),
            yaxis=dict(showgrid=False, color="#3D5A4D", autorange="reversed"),
            margin=dict(t=10, b=10, l=10, r=40),
            height=260,
        )
        st.plotly_chart(fig1, use_container_width=True)

with ch2:
    if "lineage" in df.columns:
        lin_counts = df["lineage"].value_counts().reset_index()
        lin_counts.columns = ["lineage", "count"]
        fig2 = px.pie(
            lin_counts, values="count", names="lineage",
            color="lineage", color_discrete_map=LINEAGE_COLORS,
            hole=0.5,
        )
        fig2.update_traces(
            textposition="outside", textfont_size=10,
            marker=dict(line=dict(color="#F4F1EA", width=2)),
        )
        fig2.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#3D5A4D", family="Poppins"),
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
            margin=dict(t=10, b=10, l=0, r=0),
            height=260,
        )
        st.plotly_chart(fig2, use_container_width=True)

render_footer()
