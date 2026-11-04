#Funciones de acceso a Neo4j para la página web
import re   #expresiones regulares
import streamlit as st  #para caché y lectura de credenciales
from neo4j import GraphDatabase  #driver de Neo4j

@st.cache_resource #Conexión, en caché
def get_driver():
    return GraphDatabase.driver(
        st.secrets["NEO4J_URI"],
        auth=(st.secrets["NEO4J_USER"], st.secrets["NEO4J_PASSWORD"]),
    )

_FORBIDDEN = re.compile( #Protección a la base de datos, palabras prohibidas en el cypher para evitar que visitantes modifiquen la base
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD|CALL|FOREACH)\b",
    re.IGNORECASE,
) 

def query(cypher: str, params: dict = None) -> list[dict]: #Ejecuta funciones como Cypher de solo lectura y devuleven una lista de diccionarios
    found = _FORBIDDEN.search(cypher) #busca palabras prohibidas
    if found:
        raise ValueError(f"Operación de escritura no permitida: {found.group(1).upper()}") #mensaje si se quiere hacer escritura, no permitida
    with get_driver().session() as session: #abre sesión
        return session.execute_read( #transacción de solo lectura
            lambda tx: [dict(r) for r in tx.run(cypher, params or {})] #ejecuta y convierte resultados en diccionario
        )

# Funciones para Inicio.py, conteos generales
@st.cache_data(ttl=3600) #caché de 1 hora
def get_kpis() -> dict:  
    rows = query("""
        MATCH (s:BioSample)  
        WHERE coalesce(s.is_mtb, 'Yes') = 'Yes'  
        RETURN
          count(s) AS total,
          sum(CASE WHEN s.is_mdr = 'Yes' THEN 1 ELSE 0 END) AS mdr, 
          sum(CASE WHEN s.is_xdr = 'Yes' THEN 1 ELSE 0 END) AS xdr,
          sum(CASE WHEN s.qc_pass = 'PASS' THEN 1 ELSE 0 END) AS qc_pass
    """)
    r = rows[0]
    r["mdr_rate"] = round(r["mdr"] / r["qc_pass"] * 100, 1) if r["qc_pass"] else 0
    return r

#Conteos de BioSamples para filtro, ok=resultado de TB-Profiler
@st.cache_data(ttl=3600)
def get_data_overview() -> dict: 
    s = query("""
        MATCH (s:BioSample)
        RETURN
            count(s) AS total_biosamples,
            sum(CASE WHEN s.processing_status IN ['ok', 'failed'] THEN 1 ELSE 0 END) AS with_data,
            sum(CASE WHEN s.processing_status = 'ok' THEN 1 ELSE 0 END) AS processed,
            sum(CASE WHEN s.processing_status = 'failed' THEN 1 ELSE 0 END) AS failed,
            sum(CASE WHEN s.processing_status = 'no_data' THEN 1 ELSE 0 END) AS no_data,
            sum(CASE WHEN s.processing_status = 'no_run' THEN 1 ELSE 0 END) AS no_run,
            sum(CASE WHEN s.qc_pass = 'PASS' AND s.is_mtb = 'Yes' THEN 1 ELSE 0 END) AS qc_pass,
            sum(CASE WHEN s.qc_pass = 'FAIL' THEN 1 ELSE 0 END) AS qc_fail,
            sum(CASE WHEN s.is_mtb = 'No' THEN 1 ELSE 0 END) AS no_mtb,
            sum(CASE WHEN s.is_mdr = 'Yes' AND s.is_mtb = 'Yes' THEN 1 ELSE 0 END) AS mdr,
            sum(CASE WHEN s.is_xdr = 'Yes' AND s.is_mtb = 'Yes' THEN 1 ELSE 0 END) AS xdr,
            sum(coalesce(s.n_runs, 0)) AS total_runs
    """)[0]
    s["mdr_rate"] = round(s["mdr"] / s["qc_pass"] * 100, 1) if s["qc_pass"] else 0
    return s

#A partir de aqui, todos los conteos/estadísiticas son con genomas con qc aprobado 
#Tendencia MDR por año, lee conteos ya calculados en el nodo TimePoint
@st.cache_data(ttl=3600)
def get_mdr_trend() -> list[dict]:
    return query("""
        MATCH (t:TimePoint)  
        WHERE t.sample_count > 0
        RETURN t.year AS year, t.sample_count AS total,
               t.mdr_count AS mdr, t.mdr_rate AS mdr_rate
        ORDER BY t.year
    """)

# Linajes y sublinajes
@st.cache_data(ttl=3600)
def get_lineage_dist() -> list[dict]: #conteos por linajes
    return query("""
        MATCH (l:Lineage)
        OPTIONAL MATCH (s:BioSample {qc_pass: 'PASS', is_mtb: 'Yes'})-[:BELONGS_TO]->(l)
        WITH l, collect(DISTINCT s.sub_lineage) AS subs
        RETURN l.lineage_id AS lineage, l.sample_count AS count,
               l.top_level AS top_level, l.description AS description,
               subs AS sub_lineages
        ORDER BY count DESC
    """)

@st.cache_data(ttl=3600)
def get_lineage_by_year() -> list[dict]:  #linajes por año
    return query("""
        MATCH (s:BioSample {qc_pass: 'PASS', is_mtb: 'Yes'})-[:BELONGS_TO]->(lin:Lineage),
              (s)-[:DETECTED_IN]->(t:TimePoint)
        RETURN t.year AS year, lin.top_level AS lineage, count(s) AS n
        ORDER BY year, n DESC
    """)

#Mapa, obtiene conteo de casos totales, MDR y XDR por estado 
@st.cache_data(ttl=3600)
def get_cases_by_state() -> list[dict]:
    return query("""
        MATCH (s:BioSample {qc_pass: 'PASS', is_mtb: 'Yes'})-[:COLLECTED_IN]->(l:Location)
        WHERE l.state <> ''
        RETURN l.state AS state,
               count(s) AS total,
               sum(CASE WHEN s.is_mdr = 'Yes' THEN 1 ELSE 0 END) AS mdr,
               sum(CASE WHEN s.is_xdr = 'Yes' THEN 1 ELSE 0 END) AS xdr,
               l.lat AS lat,
               l.lon AS lon
        ORDER BY total DESC
    """)

# Resistencia, conteo de muestras por categoría de resistencia basado en drtype de TB-Profiler
@st.cache_data(ttl=3600)
def get_resistance_profile() -> list[dict]:
    return query("""
        MATCH (s:BioSample)
        WHERE s.drtype IS NOT NULL AND s.drtype <> '' AND s.drtype <> 'Low_coverage'
          AND s.is_mtb = 'Yes'
        RETURN
            s.drtype AS drtype,
            count(s) AS count
        ORDER BY count DESC
    """)

#Farmacorresistencia, conteo y clasificación de la OMS
@st.cache_data(ttl=3600)
def get_drug_resistance_counts() -> list[dict]:
    return query("""
        MATCH (s:BioSample {is_mtb: 'Yes'})-[:RESISTANT_TO]->(d:Drug)
        RETURN d.name AS drug, d.drug_class AS drug_class, count(s) AS count
        ORDER BY count DESC
    """)

# Mutaciones, 
@st.cache_data(ttl=3600)
def get_top_dr_mutations(limit: int = 20, drugs: tuple = ()) -> list[dict]: #Mutaciones mas frecuentes
    return query("""
        MATCH (s:BioSample {is_mtb: 'Yes'})-[:HAS_MUTATION]->(m:Mutation {variant_class: 'dr_variant'})
              -[c:CONFERS_RESISTANCE]->(d:Drug)
        WHERE m.gene IS NOT NULL AND m.gene <> ''   // descarta mutaciones sin nombre de gen
          AND (size($drugs) = 0 OR d.name IN $drugs)
        WITH m,         // Un nodo por mutación
             collect(DISTINCT d.name) AS drugs,
             collect(DISTINCT c.confidence) AS confidences,
             count(DISTINCT s) AS sample_count
        RETURN m.gene AS gene,
               CASE WHEN m.aa_change <> '' THEN m.aa_change ELSE m.nt_change END AS change, //datos de la mutación
               drugs, confidences, sample_count
        ORDER BY sample_count DESC
        LIMIT $limit
    """, {"limit": limit, "drugs": list(drugs)})

@st.cache_data(ttl=3600)
def get_mutation_network(min_samples: int = 5) -> list[dict]: #datos de la red y mapa de calor
    return query("""
        MATCH (s:BioSample {is_mtb: 'Yes'})-[:HAS_MUTATION]->(m:Mutation {variant_class: 'dr_variant'})
              -[:CONFERS_RESISTANCE]->(d:Drug)
        WITH m, d, count(DISTINCT s) AS n  //agrupa mutación-fármaco
        WHERE n >= $min_samples  //condición filtro del usuario
        RETURN m.mutation_id  AS mut_id,
               m.gene AS gene,
               m.aa_change AS aa_change,
               d.name AS drug,
               d.drug_class AS drug_class,
               n AS sample_count
        ORDER BY n DESC
    """, {"min_samples": min_samples})

@st.cache_data(ttl=3600)
def get_other_variants(limit: int = 20) -> dict: #Otras variantes no asociadas a resistencia por catalogo OMS
    resumen = query("""
        MATCH (s:BioSample {qc_pass: 'PASS', is_mtb: 'Yes'})-[:HAS_MUTATION]->
              (m:Mutation {variant_class: 'other_variant'})
        RETURN count(DISTINCT m) AS variantes, count(DISTINCT m.gene) AS genes,
               count(DISTINCT s) AS muestras
    """)[0]
    top = query("""
        MATCH (s:BioSample {qc_pass: 'PASS', is_mtb: 'Yes'})-[:HAS_MUTATION]->
              (m:Mutation {variant_class: 'other_variant'})
        WITH m, count(DISTINCT s) AS sample_count
        RETURN m.gene AS gene,
               CASE WHEN m.aa_change <> '' THEN m.aa_change ELSE m.nt_change END AS change,
               m.variant_type AS variant_type, sample_count
        ORDER BY sample_count DESC, gene
        LIMIT $limit
    """, {"limit": limit})
    return {**resumen, "top": top}

#Filtros para la pestaña de Muestras, filtros como condiciones WHERE
@st.cache_data(ttl=3600)
def get_samples_table(
    drtype_filter: list = None,
    state_filter: str = None,
    year_filter: int = None,
    qc_only: bool = True,
) -> list[dict]:
    # Los genomas que no son M. tuberculosis (M. bovis) se excluyen de todos los análisis
    where_clauses = ["coalesce(s.is_mtb, 'Yes') = 'Yes'"]
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

    where_str = "WHERE " + " AND ".join(where_clauses) if where_clauses else "" #une condiciones
    
    return query(f"""
        MATCH (s:BioSample)
        OPTIONAL MATCH (s)-[:COLLECTED_IN]->(l:Location)
        OPTIONAL MATCH (s)-[:BELONGS_TO]->(lin:Lineage)
        OPTIONAL MATCH (s)-[:DETECTED_IN]->(t:TimePoint)
        WITH s, l, lin, t
        {where_str}
        OPTIONAL MATCH (s)-[:HAS_RUN]->(r:SRARun)
        OPTIONAL MATCH (s)-[:RESISTANT_TO]->(d:Drug)
        WITH s, l, lin, t, r, collect(d.name) AS drugs
        RETURN s.biosample_id AS sample_id,
               s.selected_run AS run_id,
               s.drtype AS drtype,
               coalesce(lin.lineage_id, s.sub_lineage) AS lineage,
               s.sub_lineage AS sub_lineage,
               s.is_mdr AS is_mdr,
               s.is_xdr AS is_xdr,
               reduce(txt = '', x IN drugs |
                      txt + CASE WHEN txt = '' THEN '' ELSE '; ' END + x) AS resistant_drugs,
               r.median_depth AS median_depth,
               s.isolation_source AS isolation_source,
               l.state AS state,
               t.year AS year,
               s.collection_date AS collection_date
        ORDER BY s.biosample_id
        LIMIT 2000
    """, params)

#Filtros para los menús desplegables
@st.cache_data(ttl=3600)
def get_states() -> list[str]: #todos los estados
    rows = query("""
        MATCH (l:Location) WHERE l.state <> ''
        RETURN l.state AS state ORDER BY state
    """)
    return ["Todos"] + [r["state"] for r in rows]

@st.cache_data(ttl=3600)
def get_drtypes() -> list[str]: #categorias de resistencia
    rows = query("""
        MATCH (s:BioSample)
        WHERE s.drtype IS NOT NULL AND s.drtype <> '' AND s.is_mtb = 'Yes'
        RETURN DISTINCT s.drtype AS drtype ORDER BY drtype
    """)
    return [r["drtype"] for r in rows]

@st.cache_data(ttl=3600)
def get_years() -> list[int]: #años con muestras
    rows = query("""
        MATCH (t:TimePoint) RETURN t.year AS year ORDER BY year
    """)
    return [r["year"] for r in rows]
