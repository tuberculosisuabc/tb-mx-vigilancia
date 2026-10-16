import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import get_lineage_dist
from utils import (AXIS_GRID, AXIS_PLAIN, BG, LINEAGE_COLORS, LINEAGE_DESCRIPTIONS, TEXT_DARK,
                   TEXT_MUTED, lineage_es, page_header, render_footer, section, setup_page,
                   show_fig, style_fig, sublineage_es)

setup_page("Linajes")

page_header(
    "Distribución de Linajes",
    """Linajes y sub-linajes de <i>M. tuberculosis</i> identificados con TB-Profiler en los genomas
    con QC aprobado.""",
)

# ── Datos: nombres y descripciones en español ────────────────────────
df_lin = pd.DataFrame(get_lineage_dist())
df_lin = df_lin[df_lin["count"].fillna(0) > 0].copy()
# Las infecciones mixtas ("lineage2;lineage4") se agrupan en una sola categoría
df_lin["lineage"] = df_lin["lineage"].map(lineage_es)
df_lin["sub_lineages"] = df_lin["sub_lineages"].apply(
    lambda subs: [sublineage_es(s) for s in subs if s] if isinstance(subs, list) else []
)
df_lin = (df_lin.groupby("lineage", as_index=False)
          .agg(count=("count", "sum"),
               sub_lineages=("sub_lineages", lambda x: sorted({s for subs in x for s in subs})))
          .sort_values("count", ascending=False))
df_lin["description"]  = df_lin["lineage"].map(LINEAGE_DESCRIPTIONS).fillna(df_lin["lineage"])
df_lin["sub_lineages"] = df_lin["sub_lineages"].apply(lambda subs: ", ".join(subs) or "—")

# ── Distribución global ──────────────────────────────────────────────
section("Distribución Global")

col1, col2 = st.columns(2)

with col1:
    fig_donut = px.pie(df_lin, values="count", names="lineage", hole=0.55,
                       color="lineage", color_discrete_map=LINEAGE_COLORS,
                       custom_data=["description"])
    fig_donut.update_traces(
        textposition="outside",
        textfont_size=11,
        hovertemplate="<b>%{label}</b><br>%{customdata[0]}<br>Muestras: %{value}<br>%{percent}<extra></extra>",
        marker=dict(line=dict(color=BG, width=2)),
    )
    style_fig(fig_donut, height=500, margin=dict(t=30, b=30, l=0, r=0), legend=dict(orientation="v"),
              annotations=[dict(text=f"<b>{df_lin['count'].sum()}</b><br>genomas", x=0.5, y=0.5,
                                font_size=13, font_color=TEXT_DARK, showarrow=False)])
    show_fig(fig_donut)

with col2:
    fig_bar = go.Figure(go.Bar(
        y=df_lin["lineage"],
        x=df_lin["count"],
        orientation="h",
        marker_color=[LINEAGE_COLORS.get(l, "#64748b") for l in df_lin["lineage"]],
        text=df_lin["count"],
        textposition="outside",
        textfont=dict(color=TEXT_MUTED, size=11),
        customdata=df_lin[["description", "sub_lineages"]].values,
        hovertemplate=("<b>%{y}</b><br>%{customdata[0]}<br>"
                       "Muestras: %{x}<br>Sub-linajes: %{customdata[1]}<extra></extra>"),
    ))
    style_fig(fig_bar, height=320, margin=dict(t=10, b=10, l=10, r=60),
              xaxis=AXIS_GRID, yaxis=dict(AXIS_PLAIN, autorange="reversed"))
    show_fig(fig_bar)

# ── Detalle ──────────────────────────────────────────────────────────
section("Detalle de Linajes")

df_display = df_lin[["lineage", "description", "count", "sub_lineages"]].copy()
df_display.columns = ["Linaje", "Descripción", "Muestras", "Sub-linajes observados"]

st.dataframe(
    df_display,
    use_container_width=True, hide_index=True,
    column_config={
        "Muestras": st.column_config.ProgressColumn(
            "Muestras", min_value=0, max_value=int(df_lin["count"].max())
        ),
    },
)

render_footer()
