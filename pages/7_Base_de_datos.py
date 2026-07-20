import streamlit as st
from utils import render_topnav, render_footer
import pandas as pd

st.set_page_config(
    page_title="Base de datos · SVG-TB-MX",
    page_icon="🫁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

render_topnav("Base de datos")

# ── Header ────────────────────────────────────────────────────────────
st.markdown("""
    <h1>Base de Datos</h1>
    <p style='color:#4a6278;font-size:1.05rem;line-height:1.7'>
        Grafo de vigilancia genómica de <em>Mycobacterium tuberculosis</em> en México, alojado en Neo4j AuraDB.
        Neo4j es una base de datos de grafos que usa el lenguaje Cypher para consultar y visualizar datos.
        Permite hacer consultas avanzadas sin descargar nada, a través de su navegador público.
    </p>
""", unsafe_allow_html=True)

# ── Neo4j connection (shared from db.py) ──────────────────────────────
from db import get_driver

@st.cache_data(ttl=3600)
def fetch_stats():
    driver = get_driver()
    with driver.session() as s:
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


# ── Stats ─────────────────────────────────────────────────────────────
st.markdown("<div class='section-header'>Resumen</div>", unsafe_allow_html=True)

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

# ── Nodes table ───────────────────────────────────────────────────────
st.markdown("<div class='section-header'>Nodos y propiedades</div>", unsafe_allow_html=True)

nodes_data = pd.DataFrame([
    ("SRARun",       "run_id",         "run_id, spots (int), has_data, collection_date, isolation_source, state, lat, lon, lineage, sub_lineage, drtype, is_mdr, is_xdr, is_mtb, median_depth, pct_mapped, qc_pass, qc_warnings, fail_reasons, num_dr_variants, num_other_variants, tb_profiler_version, db_version"),
    ("BioSample",    "biosample_id",   "biosample_id, publication_date, submission_date, status, sra_ids, owner, submitter, sample_name, strain"),
    ("Host",         "host_id",        "host_id, host_type, host_sex, host_age, host_disease"),
    ("Institution",  "institution_id", "institution_id, name, submitter"),
    ("Location",     "state",          "state, country, lat, lon"),
    ("BioProject",   "bioproject_id",  "bioproject_id, study_id"),
    ("Lineage",      "lineage_id",     "lineage_id, top_level, description, sub_lineages, sample_count (int)"),
    ("TimePoint",    "timepoint_id",   "timepoint_id, year, sample_count, mdr_count, mdr_rate"),
    ("Cluster",      "cluster_id",     "cluster_id, size, mdr_count, mdr_rate, states, lineages, first_year, last_year, span_years"),
    ("Drug",         "name",           "name, drug_class"),
    ("Mutation",     "mutation_id",    "mutation_id, gene, aa_change, nt_change, variant_type, genome_pos, confidence, who_confidence, variant_class, drug"),
], columns=["Nodo", "Clave (Key)", "Propiedades"])

st.dataframe(
    nodes_data, use_container_width=True, hide_index=True,
    column_config={
        "Nodo":         st.column_config.TextColumn(width="small"),
        "Clave (Key)":  st.column_config.TextColumn(width="small"),
        "Propiedades":  st.column_config.TextColumn(width="large"),
    }
)

# ── Relationships table ───────────────────────────────────────────────
st.markdown("<div class='section-header'>Relaciones</div>", unsafe_allow_html=True)

rels_data = pd.DataFrame([
    ("BioSample", "[:HAS_RUN]",          "SRARun",    "—"),
    ("BioSample", "[:SUBMITTED_BY]",      "Institution","—"),
    ("SRARun",    "[:FROM_HOST]",         "Host",      "—"),
    ("SRARun",    "[:COLLECTED_IN]",      "Location",  "—"),
    ("SRARun",    "[:PART_OF]",           "BioProject","—"),
    ("SRARun",    "[:BELONGS_TO]",        "Lineage",   "—"),
    ("SRARun",    "[:DETECTED_IN]",       "TimePoint", "—"),
    ("SRARun",    "[:IN_CLUSTER]",        "Cluster",   "—"),
    ("SRARun",    "[:RESISTANT_TO]",      "Drug",      "confidence, who_confidence"),
    ("SRARun",    "[:HAS_MUTATION]",      "Mutation",  "allele_freq (float), variant_depth (int), drug, variant_class"),
    ("Mutation",  "[:CONFERS_RESISTANCE]","Drug",      "confidence, who_confidence"),
    ("SRARun",    "[:LINKED_TO]",         "SRARun",    "snp_dist (int) ≤12 SNPs"),
    ("TimePoint", "[:NEXT]",              "TimePoint", "—"),
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

# ── Neo4j Cypher ──────────────────────────────────────────────
st.markdown("<div class='section-header'>Explorar a traves de Neo4j Cypher</div>", 
            unsafe_allow_html=True)

st.markdown("""
<p style='color:#4a6278;font-size:0.9rem;line-height:1.7'>
    Escribe una consulta Cypher de solo lectura (<code>MATCH</code>) 
    para explorar el grafo directamente.
</p>
""", unsafe_allow_html=True)

default_query = """MATCH (s:SRARun)-[:RESISTANT_TO]->(d:Drug)
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
        from db import query as run_query
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

# ── Ejemlos de consultas a traves de Neo4j cypher───────────────────────────────────────────────────
st.markdown("<div class='section-header'>Ejemplos de consultas a traves de Neo4j cyphe/div>", unsafe_allow_html=True)

q1, q2 = st.columns(2)
with q1:
    st.markdown("**Tendencia MDR por año**")
    st.code("""MATCH (t:TimePoint)
WHERE t.sample_count > 0
RETURN t.year, t.mdr_rate
ORDER BY t.year""", language="cypher")

    st.markdown("**Linajes en un estado**")
    st.code("""MATCH (r:SRARun)-[:COLLECTED_IN]->(l:Location {state:'Guerrero'})
MATCH (r)-[:BELONGS_TO]->(lin:Lineage)
RETURN lin.lineage_id, count(r) AS n
ORDER BY n DESC""", language="cypher")

with q2:
    st.markdown("**Clústeres de transmisión activos**")
    st.code("""MATCH (c:Cluster)
WHERE c.mdr_rate > 0
RETURN c.cluster_id, c.size, c.states, c.mdr_rate
ORDER BY c.size DESC""", language="cypher")

    st.markdown("**Mutaciones más frecuentes**")
    st.code("""MATCH (r:SRARun)-[:HAS_MUTATION]->(m:Mutation)
RETURN m.gene, m.aa_change, count(r) AS n
ORDER BY n DESC LIMIT 10""", language="cypher")

render_footer()
