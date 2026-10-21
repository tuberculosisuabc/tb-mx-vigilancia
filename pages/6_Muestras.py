import pandas as pd
import plotly.express as px
import streamlit as st

from db import get_drtypes, get_samples_table, get_states, get_years
from utils import (AXIS_GRID, AXIS_PLAIN, BG, DRTYPE_COLORS, DRTYPE_ICONS, DRTYPE_LABELS,
                   LINEAGE_COLORS, drtype_es, drug_es, lineage_es, page_header, render_footer,
                   section, setup_page, show_fig, style_fig, sublineage_es)

setup_page("Muestras")

page_header("Explorador de Muestras", "Filtra y explora los aislamientos secuenciados.")

# ── Filtros ──────────────────────────────────────────────────────────
section("Filtros")

f1, f2, f3, f4 = st.columns(4)
with f1:
    state_sel = st.selectbox("Estado", get_states())
with f2:
    # Ordenados de menor a mayor resistencia (orden de DRTYPE_LABELS en utils.py)
    orden      = list(DRTYPE_LABELS)
    drtypes    = sorted(get_drtypes(), key=lambda d: orden.index(d) if d in orden else len(orden))
    drtype_sel = st.multiselect("Perfil de resistencia", drtypes, default=drtypes,
                                format_func=drtype_es)
with f3:
    year_sel = st.selectbox("Año de colección", ["Todos"] + [str(y) for y in get_years()])
with f4:
    qc_only = st.checkbox("Solo genomas con QC aprobado", value=True)

# ── Datos ────────────────────────────────────────────────────────────
with st.spinner("Cargando muestras..."):
    df = pd.DataFrame(get_samples_table(
        drtype_filter=drtype_sel or None,
        state_filter=state_sel,
        year_filter=int(year_sel) if year_sel != "Todos" else None,
        qc_only=qc_only,
    ))

section(f"{len(df)} muestras encontradas")

if df.empty:
    st.warning("No hay muestras con los filtros seleccionados.")
    st.stop()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total",   len(df))
k2.metric("TB-MDR",  int((df["is_mdr"] == "Yes").sum()))
k3.metric("TB-XDR",  int((df["is_xdr"] == "Yes").sum()))
k4.metric("Estados", df.loc[df["state"].fillna("") != "", "state"].nunique())

# Valores de la base (en inglés) a etiquetas en español
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
    "sample_id":       "BioSample",
    "run_id":          "Run SRA",
    "drtype_icon":     "Resistencia",
    "lineage":         "Linaje",
    "sub_lineage":     "Sub-linaje",
    "state":           "Estado",
    "year":            "Año",
    "median_depth":    "Profundidad",
    "resistant_drugs": "Fármacos resist.",
}
st.dataframe(
    df[list(display_cols)].rename(columns=display_cols),
    use_container_width=True,
    hide_index=True,
    height=480,
    column_config={
        "BioSample":        st.column_config.TextColumn(width="small"),
        "Run SRA":          st.column_config.TextColumn(width="small"),
        "Resistencia":      st.column_config.TextColumn(width="medium"),
        "Año":              st.column_config.TextColumn(width="small"),
        "Profundidad":      st.column_config.NumberColumn(format="%.1f×", width="small"),
        "Fármacos resist.": st.column_config.TextColumn(width="large"),
    },
)

# ── Distribución en la selección actual ──────────────────────────────
section("Distribución en Selección Actual")

ch1, ch2 = st.columns(2)

with ch1:
    drtype_counts = df["drtype"].value_counts().rename_axis("drtype").reset_index(name="count")
    fig1 = px.bar(drtype_counts, x="count", y="drtype", orientation="h",
                  color="drtype", color_discrete_map=DRTYPE_COLORS,
                  labels={"count": "Muestras", "drtype": ""})
    style_fig(fig1, height=260, margin=dict(t=10, b=10, l=10, r=40), showlegend=False,
              xaxis=AXIS_GRID, yaxis=dict(AXIS_PLAIN, autorange="reversed"))
    show_fig(fig1)

with ch2:
    lin_counts = df["lineage"].value_counts().rename_axis("lineage").reset_index(name="count")
    fig2 = px.pie(lin_counts, values="count", names="lineage", hole=0.5,
                  color="lineage", color_discrete_map=LINEAGE_COLORS)
    fig2.update_traces(textposition="outside", textfont_size=10,
                       marker=dict(line=dict(color=BG, width=2)))
    style_fig(fig2, height=260, margin=dict(t=10, b=10, l=0, r=0), legend=dict(font=dict(size=10)))
    show_fig(fig2)

render_footer()
