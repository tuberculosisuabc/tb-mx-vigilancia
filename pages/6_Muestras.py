import streamlit as st
import plotly.express as px
import pandas as pd
from db import get_samples_table, get_states, get_drtypes, get_years
from utils import render_topnav, render_footer, render_sample_size

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
    <p style='color:#4a6278;font-size:1.05rem;line-height:1.7'>
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
    drtypes    = get_drtypes()
    drtype_sel = st.multiselect("Perfil de resistencia", drtypes, default=drtypes)
with f3:
    years    = get_years()
    year_sel = st.selectbox("Año de colección", ["Todos"] + [str(y) for y in years])
with f4:
    qc_only = st.checkbox("Solo QC PASS", value=True)

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
k2.metric("MDR",     int((df["is_mdr"] == "Yes").sum()))
k3.metric("XDR",     int((df["is_xdr"] == "Yes").sum()))
k4.metric("Estados", df["state"].nunique())

drtype_colors = {
    "Sensitive":    "🟢",
    "HR-TB":        "🟡",
    "RR-TB":        "🟠",
    "MDR-TB":       "🔴",
    "Pre-XDR-TB":   "🟣",
    "XDR-TB":       "⚫",
    "Other":        "⚪",
    "Low_coverage": "⬜",
}
df["drtype_icon"] = df["drtype"].map(drtype_colors).fillna("⚪") + " " + df["drtype"].fillna("")

display_cols = {
    "sample_id":       "ID Muestra",
    "drtype_icon":     "Resistencia",
    "lineage":         "Linaje",
    "sub_lineage":     "Sub-linaje",
    "state":           "Estado",
    "collection_date": "Año",
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
            color_discrete_map={
                "Sensitive":    "#22c55e",
                "HR-TB":        "#facc15",
                "MDR-TB":       "#f97316",
                "RR-TB":        "#fb923c",
                "Pre-XDR-TB":   "#ef4444",
                "XDR-TB":       "#dc2626",
                "Other":        "#64748b",
                "Low_coverage": "#334155",
            },
            labels={"count": "Muestras", "drtype": ""},
        )
        fig1.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#3D5A4D", family="Poppins"),
            showlegend=False,
            xaxis=dict(showgrid=True, gridcolor="#D5D0C4", color="#4a6278"),
            yaxis=dict(showgrid=False, color="#3D5A4D", autorange="reversed"),
            margin=dict(t=10, b=10, l=10, r=40),
            height=260,
        )
        st.plotly_chart(fig1, use_container_width=True)

with ch2:
    if "lineage" in df.columns:
        lin_counts = df["lineage"].value_counts().reset_index()
        lin_counts.columns = ["lineage", "count"]
        lineage_colors = {
            "lineage1": "#3b82f6", "lineage2": "#f59e0b",
            "lineage3": "#22c55e", "lineage4": "#2D6A4F",
            "La1":      "#fb923c", "La2":      "#e879f9",
        }
        fig2 = px.pie(
            lin_counts, values="count", names="lineage",
            color="lineage", color_discrete_map=lineage_colors,
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
