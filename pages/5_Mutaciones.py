import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from db import get_mutation_network, get_other_variants, get_top_dr_mutations
from utils import (AXIS_GRID, AXIS_PLAIN, BG, DRUG_COLORS, MULTI_DRUG_COLOR, TEXT_DARK, TEXT_MUTED,
                   confidence_es, drug_es, page_header, render_footer, section, setup_page,
                   show_fig, style_fig)

setup_page("Mutaciones")

page_header(
    "Mutaciones de Resistencia",
    "Variantes genómicas que confieren resistencia a antibióticos anti-TB.",
)

# ── Controles ────────────────────────────────────────────────────────
col1, col2, _ = st.columns([1, 1, 3])
with col1:
    top_n = st.slider("Mutaciones a mostrar", 10, 30, 20)
with col2:
    drug_filter = st.multiselect("Filtrar por fármaco", options=list(DRUG_COLORS), default=[],
                                 format_func=drug_es, placeholder="Todos los fármacos")

# ── Mutaciones más frecuentes ────────────────────────────────────────
section("Mutaciones más frecuentes")

# El filtro de fármaco se aplica en la consulta, así el top N es el de esos fármacos
with st.spinner("Cargando mutaciones..."):
    df_mut = pd.DataFrame(get_top_dr_mutations(limit=top_n, drugs=tuple(sorted(drug_filter))))

if df_mut.empty:
    st.info("No hay mutaciones de resistencia para los fármacos seleccionados.")
else:
    df_mut["label"] = df_mut["gene"] + " " + df_mut["change"].fillna("")
    df_mut["drug"] = df_mut["drugs"].apply(lambda d: ", ".join(sorted(drug_es(x) for x in d)))
    df_mut["confidence"] = df_mut["confidences"].apply(
        lambda c: ", ".join(sorted({confidence_es(x) for x in c})))
    # Color del fármaco; gris si la mutación confiere resistencia a varios
    df_mut["color"] = df_mut["drugs"].apply(
        lambda d: DRUG_COLORS.get(d[0], "#64748b") if len(d) == 1 else MULTI_DRUG_COLOR)

    fig = go.Figure(go.Bar(
        y=df_mut["label"],
        x=df_mut["sample_count"],
        orientation="h",
        marker_color=df_mut["color"],
        text=df_mut["sample_count"],
        textposition="outside",
        textfont=dict(color=TEXT_MUTED, size=10),
        customdata=df_mut[["drug", "confidence"]].values,
        hovertemplate=("<b>%{y}</b><br>Fármaco(s): %{customdata[0]}<br>"
                       "Confianza: %{customdata[1]}<br>Muestras: %{x}<extra></extra>"),
    ))
    style_fig(fig, height=max(350, top_n * 22), margin=dict(t=10, b=40, l=10, r=60),
              xaxis=dict(AXIS_GRID, title="Número de muestras"),
              yaxis=dict(AXIS_PLAIN, autorange="reversed"))
    show_fig(fig)
    st.caption("Barras en gris: mutaciones que confieren resistencia a más de un fármaco "
               "(el detalle aparece al pasar el cursor).")

# ── Red gen → fármaco ────────────────────────────────────────────────
section("Red gen → fármaco")
st.caption("Cada círculo es un gen y cada rombo un fármaco; el tamaño indica el número de muestras.")

min_s = st.slider("Mínimo de muestras para mostrar mutación", 1, 20, 5)
df_net = pd.DataFrame(get_mutation_network(min_samples=min_s))


def circle_positions(items, radius):
    """Coloca los elementos repartidos en un círculo de radio dado."""
    n = len(items)
    return {item: (radius * math.cos(2 * math.pi * i / n), radius * math.sin(2 * math.pi * i / n))
            for i, item in enumerate(items)}


if not df_net.empty:
    df_net["color"] = df_net["drug"].map(DRUG_COLORS).fillna("#64748b")
    df_net["drug"]  = df_net["drug"].map(drug_es)
    drug_color = dict(zip(df_net["drug"], df_net["color"]))
    genes = df_net["gene"].unique().tolist()
    drugs = df_net["drug"].unique().tolist()

    # Genes en el círculo exterior, fármacos en el interior
    gene_pos = circle_positions(genes, radius=2)
    drug_pos = circle_positions(drugs, radius=0.8)

    edge_x, edge_y = [], []
    for _, row in df_net.iterrows():
        gx, gy = gene_pos[row["gene"]]
        dx, dy = drug_pos[row["drug"]]
        edge_x += [gx, dx, None]
        edge_y += [gy, dy, None]

    edges = go.Scatter(x=edge_x, y=edge_y, mode="lines",
                       line=dict(width=0.8, color="#C8C4BC"),
                       hoverinfo="none", showlegend=False)

    gene_counts = df_net.groupby("gene")["sample_count"].sum()
    gene_nodes = go.Scatter(
        x=[gene_pos[g][0] for g in genes],
        y=[gene_pos[g][1] for g in genes],
        mode="markers+text",
        text=genes,
        textposition="top center",
        textfont=dict(color=TEXT_DARK, size=10),
        marker=dict(size=[max(10, min(40, gene_counts.get(g, 1) ** 0.5 * 3)) for g in genes],
                    color="#52B788", line=dict(color=BG, width=1)),
        hovertext=[f"{g}<br>{int(gene_counts.get(g, 0))} muestras" for g in genes],
        hoverinfo="text",
        name="Gen",
    )

    drug_counts = df_net.groupby("drug")["sample_count"].sum()
    drug_nodes = go.Scatter(
        x=[drug_pos[d][0] for d in drugs],
        y=[drug_pos[d][1] for d in drugs],
        mode="markers+text",
        text=drugs,
        textposition="bottom center",
        textfont=dict(color=TEXT_DARK, size=10),
        marker=dict(size=[max(12, min(45, drug_counts.get(d, 1) ** 0.5 * 4)) for d in drugs],
                    color=[drug_color.get(d, "#64748b") for d in drugs],
                    line=dict(color=BG, width=1), symbol="diamond"),
        hovertext=[f"{d}<br>{int(drug_counts.get(d, 0))} muestras" for d in drugs],
        hoverinfo="text",
        name="Fármaco",
    )

    hidden_axis = dict(showgrid=False, zeroline=False, showticklabels=False)
    fig_net = go.Figure(data=[edges, gene_nodes, drug_nodes])
    style_fig(fig_net, height=520, margin=dict(t=20, b=20, l=20, r=20),
              legend=dict(orientation="h", y=1.05), xaxis=hidden_axis, yaxis=hidden_axis)
    show_fig(fig_net)

# ── Mapa de calor gen × fármaco ──────────────────────────────────────
section("Mapa de calor gen × fármaco")

if not df_net.empty:
    pivot = df_net.pivot_table(index="gene", columns="drug", values="sample_count",
                               aggfunc="sum", fill_value=0)
    fig_heat = px.imshow(pivot, color_continuous_scale="Greens", aspect="auto",
                         labels=dict(x="Fármaco", y="Gen", color="Muestras"))
    style_fig(fig_heat, height=380, margin=dict(t=10, b=80, l=80, r=20),
              xaxis=dict(color=TEXT_MUTED, tickangle=-35), yaxis=dict(color=TEXT_MUTED),
              coloraxis_colorbar=dict(tickfont=dict(color=TEXT_MUTED), title="Muestras"))
    show_fig(fig_heat)

if not df_mut.empty:
    with st.expander("Ver tabla completa de mutaciones de resistencia"):
        st.dataframe(
            df_mut[["label", "drug", "confidence", "sample_count"]].rename(columns={
                "label": "Mutación", "drug": "Fármaco(s)",
                "confidence": "Confianza (catálogo OMS / TB-Profiler)", "sample_count": "Muestras",
            }),
            use_container_width=True, hide_index=True,
        )

# ── Otras variantes en genes de resistencia ──────────────────────────
section(
    "Otras variantes en genes de resistencia",
    """TB-Profiler también reporta variantes en los genes que analiza (~70 genes relacionados con
    resistencia) que el catálogo <b>no</b> asocia con resistencia: variantes sinónimas, marcadores de
    linaje o cambios de significado incierto. No se usan para clasificar la resistencia, pero se
    guardan en la base de datos para consultas posteriores.""",
)
VARIANT_TYPES = {
    "missense_variant":       "Cambio de aminoácido",
    "synonymous_variant":     "Sinónima",
    "upstream_gene_variant":  "Región promotora",
    "frameshift_variant":     "Corrimiento del marco de lectura",
    "stop_gained":            "Codón de paro",
    "conservative_inframe_deletion": "Deleción en marco",
    "disruptive_inframe_deletion":   "Deleción en marco",
    "conservative_inframe_insertion": "Inserción en marco",
    "disruptive_inframe_insertion":   "Inserción en marco",
    "start_lost":             "Pérdida del codón de inicio",
    "non_coding_transcript_exon_variant": "Gen no codificante",
}
otras = get_other_variants(limit=20)
o1, o2, o3 = st.columns(3)
o1.metric("Variantes distintas", f"{otras['variantes']:,}")
o2.metric("Genes", otras["genes"])
o3.metric("Muestras con al menos una", otras["muestras"])
if otras["top"]:
    df_otras = pd.DataFrame(otras["top"])
    # Tipos compuestos ("frameshift_variant&missense_variant") se traducen por su primer término
    df_otras["variant_type"] = df_otras["variant_type"].fillna("").map(
        lambda t: VARIANT_TYPES.get(t.split("&")[0], t))
    df_otras["mutacion"] = df_otras["gene"] + " " + df_otras["change"].fillna("")
    with st.expander("Ver las 20 más frecuentes"):
        st.dataframe(
            df_otras[["mutacion", "variant_type", "sample_count"]].rename(columns={
                "mutacion": "Variante", "variant_type": "Tipo", "sample_count": "Muestras"}),
            use_container_width=True, hide_index=True,
        )

render_footer()
