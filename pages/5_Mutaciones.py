import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import math
from db import get_top_dr_mutations, get_mutation_network
from utils import render_topnav, render_footer, render_sample_size

st.set_page_config(
    page_title="Mutaciones · SVG-TB-MX",
    page_icon="🫁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_topnav("Mutaciones")

# ── Header ────────────────────────────────────────────────────────────
st.markdown("""
    <h1>Mutaciones de Resistencia</h1>
    <p style='color:#4a6278;font-size:1.05rem;line-height:1.7'>
        Variantes genómicas que confieren resistencia a antibióticos anti-TB.
    </p>
""", unsafe_allow_html=True)

render_sample_size()

drug_colors = {
    "isoniazid":    "#f87171",
    "rifampicin":   "#fb923c",
    "ethambutol":   "#fbbf24",
    "pyrazinamide": "#a3e635",
    "streptomycin": "#34d399",
    "moxifloxacin": "#22d3ee",
    "levofloxacin": "#60a5fa",
    "bedaquiline":  "#a78bfa",
    "linezolid":    "#e879f9",
    "amikacin":     "#f472b6",
    "kanamycin":    "#fb7185",
    "capreomycin":  "#c084fc",
    "ethionamide":  "#86efac",
    "clofazimine":  "#7dd3fc",
    "delamanid":    "#fda4af",
}

# ── Controls ──────────────────────────────────────────────────────────
col1, col2, col3 = st.columns([1, 1, 3])
with col1:
    top_n = st.slider("Top N mutaciones", 10, 30, 20)
with col2:
    drug_filter = st.multiselect(
        "Filtrar por fármaco",
        options=list(drug_colors.keys()),
        default=[],
    )

# ── Top mutations bar chart ───────────────────────────────────────────
st.markdown("<div class='section-header'>Mutaciones Más Frecuentes</div>", unsafe_allow_html=True)

with st.spinner("Cargando mutaciones..."):
    mut_data = get_top_dr_mutations(limit=top_n)

df_mut = pd.DataFrame(mut_data)
if drug_filter:
    df_mut = df_mut[df_mut["drug"].isin(drug_filter)]

if not df_mut.empty:
    df_mut["label"] = df_mut["gene"] + " " + df_mut["aa_change"].fillna("")
    df_mut["color"] = df_mut["drug"].map(drug_colors).fillna("#64748b")

    fig = go.Figure(go.Bar(
        y=df_mut["label"],
        x=df_mut["sample_count"],
        orientation="h",
        marker_color=df_mut["color"],
        text=df_mut["sample_count"],
        textposition="outside",
        textfont=dict(color="#3D5A4D", size=10),
        customdata=df_mut[["drug", "who_confidence"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>Fármaco: %{customdata[0]}<br>"
            "WHO confidence: %{customdata[1]}<br>Muestras: %{x}<extra></extra>"
        ),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#3D5A4D", family="Poppins"),
        xaxis=dict(showgrid=True, gridcolor="#D5D0C4", color="#4a6278", title="Número de muestras"),
        yaxis=dict(showgrid=False, color="#3D5A4D", autorange="reversed"),
        margin=dict(t=10, b=40, l=10, r=60),
        height=max(350, top_n * 22),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Mutation-Drug network ─────────────────────────────────────────────
st.markdown("<div class='section-header'>Red Mutación → Fármaco</div>", unsafe_allow_html=True)
st.caption("Cada nodo representa una mutación o fármaco. El tamaño indica el número de muestras.")

min_s = st.slider("Mínimo de muestras para mostrar mutación", 1, 20, 5)
net_data = get_mutation_network(min_samples=min_s)
df_net = pd.DataFrame(net_data)

if not df_net.empty:
    genes = df_net["gene"].unique().tolist()
    drugs = df_net["drug"].unique().tolist()

    def circle_positions(items, radius, offset=0):
        n = len(items)
        positions = {}
        for i, item in enumerate(items):
            angle = 2 * math.pi * i / n + offset
            positions[item] = (radius * math.cos(angle), radius * math.sin(angle))
        return positions

    gene_pos = circle_positions(genes, radius=2)
    drug_pos = circle_positions(drugs, radius=0.8)

    edge_x, edge_y = [], []
    for _, row in df_net.iterrows():
        gx, gy = gene_pos[row["gene"]]
        dx, dy = drug_pos[row["drug"]]
        edge_x += [gx, dx, None]
        edge_y += [gy, dy, None]

    edges = go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(width=0.8, color="#C8C4BC"),
        hoverinfo="none", showlegend=False,
    )
    gene_counts = df_net.groupby("gene")["sample_count"].sum()
    gene_nodes = go.Scatter(
        x=[gene_pos[g][0] for g in genes],
        y=[gene_pos[g][1] for g in genes],
        mode="markers+text",
        text=genes,
        textposition="top center",
        textfont=dict(color="#1B3A2D", size=10),
        marker=dict(
            size=[max(10, min(40, gene_counts.get(g, 1) ** 0.5 * 3)) for g in genes],
            color="#52B788",
            line=dict(color="#F4F1EA", width=1),
        ),
        hovertext=[f"{g}<br>{int(gene_counts.get(g,0))} muestras" for g in genes],
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
        textfont=dict(color="#1B3A2D", size=10),
        marker=dict(
            size=[max(12, min(45, drug_counts.get(d, 1) ** 0.5 * 4)) for d in drugs],
            color=[drug_colors.get(d, "#64748b") for d in drugs],
            line=dict(color="#F4F1EA", width=1),
            symbol="diamond",
        ),
        hovertext=[f"{d}<br>{int(drug_counts.get(d,0))} muestras" for d in drugs],
        hoverinfo="text",
        name="Fármaco",
    )
    fig_net = go.Figure(data=[edges, gene_nodes, drug_nodes])
    fig_net.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#3D5A4D", family="Poppins"),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        legend=dict(orientation="h", y=1.05, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        margin=dict(t=20, b=20, l=20, r=20),
        height=520,
    )
    st.plotly_chart(fig_net, use_container_width=True)

# ── Heatmap ───────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>Heatmap Gen × Fármaco</div>", unsafe_allow_html=True)

if not df_net.empty:
    pivot = df_net.pivot_table(
        index="gene", columns="drug", values="sample_count",
        aggfunc="sum", fill_value=0,
    )
    fig_heat = px.imshow(
        pivot,
        color_continuous_scale="Greens",
        labels=dict(x="Fármaco", y="Gen", color="Muestras"),
        aspect="auto",
    )
    fig_heat.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#3D5A4D", family="Poppins"),
        xaxis=dict(color="#3D5A4D", tickangle=-35),
        yaxis=dict(color="#3D5A4D"),
        coloraxis_colorbar=dict(tickfont=dict(color="#3D5A4D"), title="Muestras"),
        margin=dict(t=10, b=80, l=80, r=20),
        height=380,
    )
    st.plotly_chart(fig_heat, use_container_width=True)

with st.expander("Ver tabla completa de mutaciones DR"):
    st.dataframe(
        df_mut[["label", "drug", "who_confidence", "sample_count"]].rename(columns={
            "label": "Mutación", "drug": "Fármaco",
            "who_confidence": "WHO Confidence", "sample_count": "Muestras",
        }),
        use_container_width=True, hide_index=True,
    )

render_footer()
