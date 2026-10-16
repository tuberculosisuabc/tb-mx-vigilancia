import re

import streamlit as st
from neo4j import GraphDatabase


# ── Conexión (en caché durante toda la sesión) ────────────────────────
@st.cache_resource
def get_driver():
    return GraphDatabase.driver(
        st.secrets["NEO4J_URI"],
        auth=(st.secrets["NEO4J_USER"], st.secrets["NEO4J_PASSWORD"]),
    )


# ── Consultas de solo lectura ─────────────────────────────────────────
# La protección real es execute_read: Neo4j rechaza cualquier escritura dentro
# de una transacción de lectura. La lista de palabras solo sirve para mostrar
# un mensaje claro antes de enviar la consulta.
_FORBIDDEN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|CALL|FOREACH)\b",
    re.IGNORECASE,
)


def query(cypher: str, params: dict = None) -> list[dict]:
    """Ejecuta una consulta de solo lectura y devuelve una lista de diccionarios.
    Lanza ValueError si la consulta contiene una operación de escritura."""
    found = _FORBIDDEN.search(cypher)
    if found:
        raise ValueError(f"Operación de escritura no permitida: {found.group(1).upper()}")
    with get_driver().session() as session:
        return session.execute_read(
            lambda tx: [dict(r) for r in tx.run(cypher, params or {})]
        )


# ══════════════════════════════════════════════════════════════════════
# RESUMEN — tarjetas KPI y embudo
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def get_kpis() -> dict:
    rows = query("""
        MATCH (s:SRARun)
        RETURN
          count(s)                                             AS total,
          sum(CASE WHEN s.is_mdr  = 'Yes' THEN 1 ELSE 0 END) AS mdr,
          sum(CASE WHEN s.is_xdr  = 'Yes' THEN 1 ELSE 0 END) AS xdr,
          sum(CASE WHEN s.qc_pass = 'PASS' THEN 1 ELSE 0 END) AS qc_pass
    """)
    r = rows[0]
    r["mdr_rate"] = round(r["mdr"] / r["qc_pass"] * 100, 1) if r["qc_pass"] else 0
    return r


@st.cache_data(ttl=3600)
def get_data_overview() -> dict:
    bs = query("MATCH (b:BioSample) RETURN count(b) AS total_biosamples")[0]

    sra = query("""
        MATCH (r:SRARun)
        RETURN
            count(r) AS total_sra_runs,
            sum(CASE WHEN r.spots = 0 OR r.spots IS NULL THEN 1 ELSE 0 END) AS empty_runs
    """)[0]

    s = query("""
        MATCH (s:SRARun)
        WHERE s.qc_pass IS NOT NULL
        RETURN
            count(s)                                                  AS runs_processed,
            sum(CASE WHEN s.qc_pass = 'PASS' THEN 1 ELSE 0 END)      AS qc_pass,
            sum(CASE WHEN s.qc_pass = 'FAIL' THEN 1 ELSE 0 END)      AS qc_fail_real,
            sum(CASE WHEN s.is_mtb  = 'No'   THEN 1 ELSE 0 END)      AS no_mtb,
            sum(CASE WHEN s.is_mdr  = 'Yes'  THEN 1 ELSE 0 END)      AS mdr,
            sum(CASE WHEN s.is_xdr  = 'Yes'  THEN 1 ELSE 0 END)      AS xdr
    """)[0]

    total_sra_runs    = sra["total_sra_runs"]
    empty_runs        = sra["empty_runs"]
    runs_processed    = s["runs_processed"]
    qc_pass           = s["qc_pass"]
    mdr               = s["mdr"]
    real_runs         = total_sra_runs - empty_runs
    failed_processing = max(0, real_runs - runs_processed)

    return {
        "total_biosamples" : bs["total_biosamples"],
        "total_sra_runs"   : total_sra_runs,
        "runs_processed"   : runs_processed,
        "qc_pass"          : qc_pass,
        "mdr"              : mdr,
        "xdr"              : s["xdr"],
        "mdr_rate"         : round(mdr / qc_pass * 100, 1) if qc_pass else 0,
        "empty_runs"       : empty_runs,
        "failed_processing": failed_processing,
        "qc_fail"          : s["qc_fail_real"],
        "no_mtb"           : s["no_mtb"],
        "no_sra"           : bs["total_biosamples"] - total_sra_runs,
    }


# ══════════════════════════════════════════════════════════════════════
# TENDENCIA MDR (los conteos por año ya usan solo genomas con QC aprobado)
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def get_mdr_trend() -> list[dict]:
    return query("""
        MATCH (t:TimePoint)
        WHERE t.sample_count > 0
        RETURN t.year AS year, t.sample_count AS total,
               t.mdr_count AS mdr, t.mdr_rate AS mdr_rate
        ORDER BY t.year
    """)


# ══════════════════════════════════════════════════════════════════════
# LINAJES
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def get_lineage_dist() -> list[dict]:
    return query("""
        MATCH (l:Lineage)
        OPTIONAL MATCH (s:SRARun {qc_pass: 'PASS'})-[:BELONGS_TO]->(l)
        WITH l, collect(DISTINCT s.sub_lineage) AS subs
        RETURN l.lineage_id AS lineage, l.sample_count AS count,
               l.top_level AS top_level, l.description AS description,
               subs AS sub_lineages
        ORDER BY count DESC
    """)


@st.cache_data(ttl=3600)
def get_lineage_by_year() -> list[dict]:
    return query("""
        MATCH (s:SRARun {qc_pass: 'PASS'})-[:BELONGS_TO]->(lin:Lineage),
              (s)-[:DETECTED_IN]->(t:TimePoint)
        RETURN t.year AS year, lin.top_level AS lineage, count(s) AS n
        ORDER BY year, n DESC
    """)


# ══════════════════════════════════════════════════════════════════════
# MAPA — casos por estado (solo genomas con QC aprobado)
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def get_cases_by_state() -> list[dict]:
    return query("""
        MATCH (s:SRARun {qc_pass: 'PASS'})-[:COLLECTED_IN]->(l:Location)
        WHERE l.state <> ''
        RETURN l.state AS state,
               count(s) AS total,
               sum(CASE WHEN s.is_mdr = 'Yes' THEN 1 ELSE 0 END) AS mdr,
               sum(CASE WHEN s.is_xdr = 'Yes' THEN 1 ELSE 0 END) AS xdr,
               l.lat AS lat,
               l.lon AS lon
        ORDER BY total DESC
    """)


# ══════════════════════════════════════════════════════════════════════
# RESISTENCIA / FÁRMACOS
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def get_resistance_profile() -> list[dict]:
    return query("""
        MATCH (s:SRARun)
        WHERE s.drtype IS NOT NULL AND s.drtype <> '' AND s.drtype <> 'Low_coverage'
        RETURN
            CASE WHEN s.is_mtb = 'No' THEN 'No-Mtb' ELSE s.drtype END AS drtype,
            count(s) AS count
        ORDER BY count DESC
    """)


@st.cache_data(ttl=3600)
def get_drug_resistance_counts() -> list[dict]:
    return query("""
        MATCH (s:SRARun)-[:RESISTANT_TO]->(d:Drug)
        RETURN d.name AS drug, d.drug_class AS drug_class, count(s) AS count
        ORDER BY count DESC
    """)


# ══════════════════════════════════════════════════════════════════════
# MUTACIONES
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def get_top_dr_mutations(limit: int = 20, drugs: tuple = ()) -> list[dict]:
    """Mutaciones de resistencia más frecuentes. Si se indican fármacos, el top N
    se calcula solo entre las mutaciones asociadas a esos fármacos."""
    return query("""
        MATCH (s:SRARun)-[:HAS_MUTATION]->(m:Mutation)
        WHERE m.variant_class = 'dr_variant'
          AND m.gene IS NOT NULL AND m.gene <> ''
          AND (size($drugs) = 0 OR m.drug IN $drugs)
        WITH m, count(s) AS sample_count
        RETURN m.gene AS gene,
               CASE WHEN m.aa_change <> '' THEN m.aa_change ELSE m.nt_change END AS change,
               m.drug AS drug, m.confidence AS confidence,
               sample_count
        ORDER BY sample_count DESC
        LIMIT $limit
    """, {"limit": limit, "drugs": list(drugs)})


@st.cache_data(ttl=3600)
def get_mutation_network(min_samples: int = 5) -> list[dict]:
    """Nodos y aristas de la red mutación–fármaco."""
    return query("""
        MATCH (s:SRARun)-[:HAS_MUTATION]->(m:Mutation),
              (s)-[:RESISTANT_TO]->(d:Drug)
        WHERE m.drug = d.name
          AND m.variant_class = 'dr_variant'
        WITH m, d, count(s) AS n
        WHERE n >= $min_samples
        RETURN m.mutation_id  AS mut_id,
               m.gene         AS gene,
               m.aa_change    AS aa_change,
               d.name         AS drug,
               d.drug_class   AS drug_class,
               n              AS sample_count
        ORDER BY n DESC
    """, {"min_samples": min_samples})


# ══════════════════════════════════════════════════════════════════════
# GRUPOS DE SIMILITUD (regiones de resistencia, no transmisión)
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def get_clusters() -> list[dict]:
    return query("""
        MATCH (s:SRARun)-[:IN_CLUSTER]->(c:Cluster)
        RETURN c.cluster_id AS cluster_id,
               c.size       AS size,
               collect(s.run_id) AS samples,
               sum(CASE WHEN s.is_mdr = 'Yes' THEN 1 ELSE 0 END) AS mdr_count
        ORDER BY size DESC
    """)


# ══════════════════════════════════════════════════════════════════════
# TABLA DE MUESTRAS
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def get_samples_table(
    drtype_filter: list = None,
    state_filter: str = None,
    year_filter: int = None,
    qc_only: bool = True,
) -> list[dict]:
    where_clauses = []
    params = {}
    if qc_only:
        where_clauses.append("s.qc_pass = 'PASS'")
    if drtype_filter:
        where_clauses.append("s.drtype IN $drtypes")
        params["drtypes"] = drtype_filter
    if state_filter and state_filter != "Todos":
        where_clauses.append("l.state = $state")
        params["state"] = state_filter
    if year_filter:
        where_clauses.append("t.year = $year")
        params["year"] = year_filter

    where_str = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # El WITH es necesario: un WHERE escrito justo después de OPTIONAL MATCH solo
    # condiciona ese OPTIONAL MATCH y no elimina filas, así que los filtros no se
    # aplicarían.
    return query(f"""
        MATCH (s:SRARun)
        OPTIONAL MATCH (s)-[:COLLECTED_IN]->(l:Location)
        OPTIONAL MATCH (s)-[:BELONGS_TO]->(lin:Lineage)
        OPTIONAL MATCH (s)-[:DETECTED_IN]->(t:TimePoint)
        WITH s, l, lin, t
        {where_str}
        RETURN s.run_id           AS sample_id,
               s.drtype           AS drtype,
               s.lineage          AS lineage,
               s.sub_lineage      AS sub_lineage,
               s.is_mdr           AS is_mdr,
               s.is_xdr           AS is_xdr,
               s.resistant_drugs  AS resistant_drugs,
               s.median_depth     AS median_depth,
               s.isolation_source AS isolation_source,
               l.state            AS state,
               t.year             AS year,
               s.collection_date  AS collection_date
        ORDER BY s.run_id
        LIMIT 2000
    """, params)


# ══════════════════════════════════════════════════════════════════════
# FILTROS (para los menús desplegables)
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def get_states() -> list[str]:
    rows = query("""
        MATCH (l:Location) WHERE l.state <> ''
        RETURN l.state AS state ORDER BY state
    """)
    return ["Todos"] + [r["state"] for r in rows]


@st.cache_data(ttl=3600)
def get_drtypes() -> list[str]:
    rows = query("""
        MATCH (s:SRARun)
        WHERE s.drtype IS NOT NULL AND s.drtype <> ''
        RETURN DISTINCT s.drtype AS drtype ORDER BY drtype
    """)
    return [r["drtype"] for r in rows]


@st.cache_data(ttl=3600)
def get_years() -> list[int]:
    rows = query("""
        MATCH (t:TimePoint) RETURN t.year AS year ORDER BY year
    """)
    return [r["year"] for r in rows]
