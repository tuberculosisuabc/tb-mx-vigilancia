import pandas as pd
import streamlit as st

from db import get_driver, query as run_query
from utils import page_header, render_footer, section, setup_page

setup_page("Base de datos")

page_header(
    "Base de Datos",
    """Grafo de vigilancia genómica de <em>Mycobacterium tuberculosis</em> en México, alojado en Neo4j AuraDB.
    Neo4j es una base de datos de grafos que usa el lenguaje Cypher para consultar y visualizar datos.
    Permite hacer consultas avanzadas sin descargar nada, a través de su navegador público.""",
    sample_size=False,
)


@st.cache_data(ttl=3600)
def fetch_stats():
    with get_driver().session() as s:
        total_nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        total_rels  = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        rel_types   = s.run("CALL db.relationshipTypes() YIELD relationshipType RETURN count(relationshipType) AS c").single()["c"]
        node_types  = s.run("CALL db.labels() YIELD label RETURN count(label) AS c").single()["c"]
    return {
        "node_types":  f"{node_types:,}",
        "total_nodes": f"{total_nodes:,}",
        "rel_types":   f"{rel_types:,}",
        "total_rels":  f"{total_rels:,}",
    }


# ── Resumen ─────────────────────────────────────────────────────────
section("Resumen")

try:
    stats = fetch_stats()
    c1, c2, c3, c4 = st.columns(4)
    for col, number, label in zip(
        [c1, c2, c3, c4],
        [stats["node_types"], stats["total_nodes"], stats["rel_types"], stats["total_rels"]],
        ["Tipos de nodos", "Nodos totales", "Tipos de relaciones", "Relaciones totales"],
    ):
        with col:
            st.markdown(
                f"<div class='stat-card'><div class='stat-number'>{number}</div>"
                f"<div class='stat-label'>{label}</div></div>",
                unsafe_allow_html=True,
            )
except Exception as e:
    st.warning(f"No se pudo conectar a Neo4j: {e}")

# ── Tabla de nodos ───────────────────────────────────────────────────
section("Nodos y propiedades")

# Esquema tal como lo crea pipeline/04_load_neo4j.py
nodes_data = pd.DataFrame([
    ("BioSample",  "biosample_id",  "biosample_id, selected_run, n_runs (int), n_runs_with_result (int), processing_status, processing_error, lineage, sub_lineage, drtype, is_rr, is_mdr, is_xdr, is_mtb, species, mixed_infection, resistant_drugs, median_depth, pct_mapped, qc_pass, fail_reasons, qc_warnings, num_dr_variants, num_other_variants, collection_date, isolation_source, tb_profiler_version, db_version"),
    ("SRARun",     "run_id",        "run_id, spots (int), median_depth, pct_mapped, qc_pass, tb_profiler_version, db_version (solo el run seleccionado de cada BioSample)"),
    ("Host",       "host_id",       "host_id, host_type, host_sex, host_age, host_disease"),
    ("Location",   "state",         "state, country, lat, lon"),
    ("BioProject", "bioproject_id", "bioproject_id, study_id"),
    ("Lineage",    "lineage_id",    "lineage_id, top_level, description, sample_count (int)"),
    ("TimePoint",  "timepoint_id",  "timepoint_id, year, sample_count, mdr_count, mdr_rate, rr_count, rr_rate"),
    ("Cluster",    "cluster_id",    "cluster_id, size, method, snp_threshold"),
    ("Drug",       "name",          "name, drug_class"),
    ("Mutation",   "mutation_id",   "mutation_id, gene, nt_change, aa_change, variant_type, genome_pos, confidence, who_confidence, variant_class, drug"),
], columns=["Nodo", "Clave (Key)", "Propiedades"])

st.dataframe(
    nodes_data, use_container_width=True, hide_index=True,
    column_config={
        "Nodo":         st.column_config.TextColumn(width="small"),
        "Clave (Key)":  st.column_config.TextColumn(width="small"),
        "Propiedades":  st.column_config.TextColumn(width="large"),
    }
)

# ── Tabla de relaciones ──────────────────────────────────────────────
section("Relaciones")

rels_data = pd.DataFrame([
    ("BioSample", "[:HAS_RUN]",            "SRARun",     "— (run seleccionado)"),
    ("BioSample", "[:FROM_HOST]",          "Host",       "—"),
    ("BioSample", "[:COLLECTED_IN]",       "Location",   "—"),
    ("BioSample", "[:PART_OF]",            "BioProject", "—"),
    ("BioSample", "[:BELONGS_TO]",         "Lineage",    "—"),
    ("BioSample", "[:DETECTED_IN]",        "TimePoint",  "—"),
    ("BioSample", "[:IN_CLUSTER]",         "Cluster",    "—"),
    ("BioSample", "[:RESISTANT_TO]",       "Drug",       "confidence, who_confidence"),
    ("BioSample", "[:HAS_MUTATION]",       "Mutation",   "allele_freq (float), variant_depth (int), drug, variant_class"),
    ("Mutation",  "[:CONFERS_RESISTANCE]", "Drug",       "confidence, who_confidence"),
    ("BioSample", "[:LINKED_TO]",          "BioSample",  "snp_dist (int, ≤ 12 SNPs en regiones de resistencia)"),
], columns=["Nodo de Origen", "Relación", "Nodo Final", "Propiedades"])

st.dataframe(
    rels_data, use_container_width=True, hide_index=True,
    column_config={
        "Nodo de Origen": st.column_config.TextColumn(width="small"),
        "Relación":       st.column_config.TextColumn(width="small"),
        "Nodo Final":     st.column_config.TextColumn(width="small"),
        "Propiedades":    st.column_config.TextColumn(width="small"),
    }
)

# ── Consola Cypher ───────────────────────────────────────────────────
section("Explorar a través de Neo4j Cypher")

st.markdown("""
<p class='texto' style='font-size:0.9rem'>
    Escribe una consulta Cypher de solo lectura (<code>MATCH</code>) 
    para explorar el grafo directamente.
</p>
""", unsafe_allow_html=True)

default_query = """MATCH (s:BioSample)-[:RESISTANT_TO]->(d:Drug)
RETURN d.name AS drug, count(s) AS samples
ORDER BY samples DESC
LIMIT 10"""

user_query = st.text_area(
    "Consulta Cypher",
    value=default_query,
    height=120,
    label_visibility="collapsed"
)

col_run, col_info = st.columns([1, 5])
with col_run:
    run_btn = st.button("▶ Ejecutar", type="primary", use_container_width=True)
with col_info:
    st.markdown(
        "<p style='color:#7A9A8A;font-size:0.78rem;padding-top:8px'>"
        "Solo se permiten consultas de lectura (MATCH). "
        "Las operaciones de escritura están bloqueadas.</p>",
        unsafe_allow_html=True
    )

if run_btn and user_query.strip():
    try:
        with st.spinner("Ejecutando..."):
            results = run_query(user_query)
        if results:
            st.dataframe(pd.DataFrame(results), use_container_width=True)
            st.caption(f"{len(results)} resultado(s)")
        else:
            st.info("La consulta no devolvió resultados.")
    except ValueError as e:
        st.error(f"⛔ Operación no permitida: {e}")
    except Exception as e:
        st.error(f"Error en la consulta: {e}")
st.markdown("")
st.link_button("Conoce más sobre Neo4j →", "https://neo4j.com/", type="secondary")

# ── Ejemplos de consultas Cypher ─────────────────────────────────────
section("Ejemplos de consultas Cypher")

q1, q2 = st.columns(2)
with q1:
    st.markdown("**Tendencia MDR por año**")
    st.code("""MATCH (t:TimePoint)
WHERE t.sample_count > 0
RETURN t.year, t.mdr_rate
ORDER BY t.year""", language="cypher")

    st.markdown("**Linajes en un estado**")
    st.code("""MATCH (r:BioSample)-[:COLLECTED_IN]->(l:Location {state:'Guerrero'})
MATCH (r)-[:BELONGS_TO]->(lin:Lineage)
RETURN lin.lineage_id, count(r) AS n
ORDER BY n DESC""", language="cypher")

with q2:
    st.markdown("**Grupos de similitud genotípica (regiones de resistencia)**")
    st.code("""MATCH (s:BioSample)-[:IN_CLUSTER]->(c:Cluster)
RETURN c.cluster_id, c.size,
       sum(CASE WHEN s.is_mdr = 'Yes' THEN 1 ELSE 0 END) AS mdr
ORDER BY c.size DESC""", language="cypher")
    st.caption("Agrupan genomas con genotipos similares en ~70 genes de resistencia; "
               "no indican transmisión.")

    st.markdown("**Mutaciones más frecuentes**")
    st.code("""MATCH (r:BioSample)-[:HAS_MUTATION]->(m:Mutation)
RETURN m.gene, m.aa_change, count(r) AS n
ORDER BY n DESC LIMIT 10""", language="cypher")

render_footer()
