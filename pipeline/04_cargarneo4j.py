#!/usr/bin/env python3

#Cargar CSVs de resultados a Neo4j
#Uso: python pipeline/04_cargarneo4j
import os, sys, re
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import pandas as pd
from neo4j import GraphDatabase, exceptions as neo4j_exc

# Credenciales de entorno de Neo4j
NEO4J_URI  = os.environ.get("NEO4J_URI")
NEO4J_USER = os.environ.get("NEO4J_USER") or os.environ.get("NEO4J_USERNAME")
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD")

# Rutas
METADATA_CSV     = Path.home() / "metadata_cleaned.csv"
NEO4J_EXPORT_DIR = Path.home() / "neo4j_export"
NEW_RUNS_FILE    = Path.home() / "new_runs.txt"
LOG_FILE         = Path.home() / "load_neo4j_update.log"
BATCH_SIZE       = 500

def log(msg):
    ts   = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def read_csv(filename):
    path = NEO4J_EXPORT_DIR / filename
    if not path.exists():
        log(f"  No encontrado: {filename} — omitido")
        return []
    df = pd.read_csv(path, dtype=str).fillna("")
    log(f"  {filename:<45} {len(df):>6} filas")
    return df.to_dict("records")

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def run_batch(sf, query, rows, label):
    total    = len(rows)
    inserted = 0
    for batch in chunks(rows, BATCH_SIZE):
        with sf() as session:
            session.run(query, {"rows": batch})
        inserted += len(batch)
        print(f"    {label}: {inserted}/{total} ({inserted/total*100:.0f}%)",
              end="\r", flush=True)
    print()
    log(f"  {label:<42} {inserted:>6} registros")

def parse_year(date_str):
    if not date_str or date_str.lower() in ("not collected", "missing", "na", "n/a", ""):
        return None
    m = re.search(r"\b(19|20)\d{2}\b", date_str)
    return int(m.group()) if m else None

LINEAGE_DESC = {
    "lineage1": "Indo-Oceanic (L1)",
    "lineage2": "East-Asian / Beijing (L2)",
    "lineage3": "East-African-Indian (L3)",
    "lineage4": "Euro-American (L4)",
    "lineage5": "West-African 1 (L5)",
    "lineage6": "West-African 2 (L6)",
    "lineage7": "Ethiopian (L7)",
    "lineage8": "Clade A1 (L8)",
    "lineage9": "Clade A2 (L9)",
    "La1"     : "M. africanum",
    "La2"     : "M. africanum 2",
    "QC_Failed": "QC Failed — low coverage",
}

# Conectar a Neo4J
log("=" * 60)
log("CARGA INCREMENTAL A NEO4J")
log(f"URI: {NEO4J_URI}")

try:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    driver.verify_connectivity()
    log("Conexión exitosa a Neo4j ")
except Exception as e:
    log(f"ERROR conectando a Neo4j: {e}")
    sys.exit(1)

sf = driver.session  # session factory

# Leer runs nuevos
new_runs = set()
if NEW_RUNS_FILE.exists():
    new_runs = {r.strip() for r in NEW_RUNS_FILE.read_text().splitlines() if r.strip()}
log(f"Runs nuevos a cargar: {len(new_runs)}")

# Cargar metadata
log("\nCargando metadata CSV...")
df_meta_all = pd.read_csv(METADATA_CSV, dtype=str).fillna("")
df_meta = (df_meta_all[df_meta_all["Run"] != ""].copy()
           .assign(_c=(df_meta_all[df_meta_all["Run"] != ""] != "").sum(axis=1))
           .sort_values("_c", ascending=False)
           .drop_duplicates(subset="Run")
           .drop(columns="_c")
           .reset_index(drop=True))

# Filtrar solo los nuevos
df_meta_new = df_meta[df_meta["Run"].isin(new_runs)].copy()
log(f"  Runs nuevos en metadata: {len(df_meta_new)}")

# Leer CSVs generados
log("\nLeyendo CSVs de neo4j_export/...")
sample_tbp_rows = read_csv("neo4j_nodes_sample.csv")
df_tbp = pd.DataFrame(sample_tbp_rows) if sample_tbp_rows else pd.DataFrame()

date_lookup = (df_meta.set_index("Run")["collection_date"].fillna("").to_dict()
               if "collection_date" in df_meta.columns else {})

# PASO 1: Nodos de metadata (Location, BioProject, BioSample, Host)
log("\n" + "=" * 60)
log("PASO 1: Nodos de metadata")

location_rows   = []
bioproject_rows = []
biosample_rows  = []
host_rows       = []
sample_meta_rows = []
seen_locations   = set()
seen_bioprojects = set()

for _, row in df_meta_new.iterrows():
    run   = row.get("Run", "")
    state = row.get("state", "")
    bp    = row.get("BioProject_y", "")
    bs_id = row.get("BioSampleID", "")
    geo   = row.get("geo_loc_name", "")

    if state and state not in seen_locations:
        try:
            lat_raw = row.get("lat", "")
            lon_raw = row.get("lon", "")
            lat = float(lat_raw) if lat_raw else None
            lon = float(lon_raw) if lon_raw else None
        except ValueError:
            lat = lon = None
        location_rows.append({
            "state": state, "country": geo.split(":")[0].strip() if geo else "Mexico",
            "lat": lat, "lon": lon,
        })
        seen_locations.add(state)

    if bp and bp not in seen_bioprojects:
        bioproject_rows.append({
            "bioproject_id": bp,
            "study_id"     : row.get("SRAStudy", ""),
        })
        seen_bioprojects.add(bp)

    if bs_id:
        biosample_rows.append({"biosample_id": bs_id})
        host_rows.append({
            "host_id"     : bs_id,
            "host_type"   : row.get("host", ""),
            "host_sex"    : row.get("host_sex", ""),
            "host_age"    : row.get("host_age", ""),
            "host_disease": row.get("host_disease", ""),
        })

    if run:
        sample_meta_rows.append({
            "sample_id"       : run,
            "biosample_id"    : bs_id,
            "bioproject_id"   : bp,
            "collection_date" : row.get("collection_date", ""),
            "host_sex"        : row.get("host_sex", ""),
            "host_age"        : row.get("host_age", ""),
            "host_disease"    : row.get("host_disease", ""),
            "isolation_source": row.get("isolation_source", ""),
            "state"           : state,
            "lat"             : row.get("lat", ""),
            "lon"             : row.get("lon", ""),
            "spots"           : row.get("spots", "0"),
        })

if location_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (l:Location {state: row.state})
        SET l.country = row.country,
            l.lat     = CASE WHEN row.lat IS NOT NULL THEN toFloat(row.lat) ELSE l.lat END,
            l.lon     = CASE WHEN row.lon IS NOT NULL THEN toFloat(row.lon) ELSE l.lon END
    """, location_rows, "Location nodes")

if bioproject_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (p:BioProject {bioproject_id: row.bioproject_id})
        SET p.study_id = row.study_id
    """, bioproject_rows, "BioProject nodes")

if biosample_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (b:BioSample {biosample_id: row.biosample_id})
    """, biosample_rows, "BioSample nodes")

if host_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (h:Host {host_id: row.host_id})
        SET h.host_type    = row.host_type,
            h.host_sex     = row.host_sex,
            h.host_age     = row.host_age,
            h.host_disease = row.host_disease
    """, host_rows, "Host nodes")

# SRARun base (spots)
srarun_base = [{"run_id": r["sample_id"], "spots": r.get("spots", "0")}
               for r in sample_meta_rows]
if srarun_base:
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (s:SRARun {run_id: row.run_id})
        SET s.spots   = CASE WHEN row.spots <> '' THEN toInteger(row.spots) ELSE 0 END,
            s.has_data = CASE WHEN row.spots <> '0' THEN 'Yes' ELSE 'No' END
    """, srarun_base, "SRARun base nodes")

#PASO 2: Lineage y TimePoint
log("\n" + "=" * 60)
log("PASO 2: Lineage y TimePoint")

lineage_map      = defaultdict(lambda: {"sub_lineages": set(), "count": 0})
belongs_to_rows  = []
detected_in_rows = []

if not df_tbp.empty:
    for _, row in df_tbp.iterrows():
        lin = row.get("lineage", "")
        sub = row.get("sub_lineage", "")
        sid = row.get("sample_id", "")
        if lin and lin not in ("", "QC_Failed"):
            top = lin.split(".")[0]
            lineage_map[lin]["sub_lineages"].add(sub)
            lineage_map[lin]["top_level"] = top
            lineage_map[lin]["count"] += 1
            belongs_to_rows.append({"sample_id": sid, "lineage_id": lin})

        date_str = date_lookup.get(sid, "")
        year     = parse_year(date_str)
        if year:
            detected_in_rows.append({
                "sample_id"   : sid,
                "timepoint_id": str(year),
                "year"        : year,
            })

lineage_rows = []
for lin, info in lineage_map.items():
    top = lin.split(".")[0]
    lineage_rows.append({
        "lineage_id" : lin,
        "top_level"  : top,
        "description": LINEAGE_DESC.get(lin, LINEAGE_DESC.get(top, "")),
    })

if lineage_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (l:Lineage {lineage_id: row.lineage_id})
        SET l.top_level   = row.top_level,
            l.description = row.description
    """, lineage_rows, "Lineage nodes")

timepoint_rows = {r["timepoint_id"]: r["year"] for r in detected_in_rows}
tp_rows = [{"timepoint_id": tid, "year": yr} for tid, yr in timepoint_rows.items()]
if tp_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (t:TimePoint {timepoint_id: row.timepoint_id})
        SET t.year = toInteger(row.year)
    """, tp_rows, "TimePoint nodes")

#PASO 3: Clusters
log("\n" + "=" * 60)
log("PASO 3: Clusters")

cluster_rows_csv = read_csv("transmission_clusters.csv")
cluster_nodes    = {}
for r in cluster_rows_csv:
    cid = r.get("cluster_id", "")
    if cid and cid != "singleton":
        cluster_nodes[cid] = r.get("cluster_size", "1")

if cluster_nodes:
    cn_rows = [{"cluster_id": k, "size": v} for k, v in cluster_nodes.items()]
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (c:Cluster {cluster_id: row.cluster_id})
        SET c.size = toInteger(row.size)
    """, cn_rows, "Cluster nodes")

in_cluster_rows = [
    {"sample_id": r["sample_id"], "cluster_id": r["cluster_id"]}
    for r in cluster_rows_csv
    if r.get("cluster_id", "") != "singleton"
]

#PASO 4: Relaciones de metadata
log("\n" + "=" * 60)
log("PASO 4: Relaciones de metadata")

# HAS_RUN
has_run = [{"biosample_id": r["biosample_id"], "run_id": r["sample_id"]}
           for r in sample_meta_rows if r.get("biosample_id")]
if has_run:
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (b:BioSample {biosample_id: row.biosample_id})
        MATCH (r:SRARun    {run_id:       row.run_id})
        MERGE (b)-[:HAS_RUN]->(r)
    """, has_run, "HAS_RUN rels")

# FROM_HOST
from_host = [{"sample_id": r["sample_id"], "biosample_id": r["biosample_id"]}
             for r in sample_meta_rows if r.get("biosample_id")]
if from_host:
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (r:SRARun {run_id:   row.sample_id})
        MATCH (h:Host   {host_id:  row.biosample_id})
        MERGE (r)-[:FROM_HOST]->(h)
    """, from_host, "FROM_HOST rels")

# COLLECTED_IN
has_loc = [r for r in sample_meta_rows if r.get("state")]
if has_loc:
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (r:SRARun   {run_id: row.sample_id})
        MATCH (l:Location {state:  row.state})
        MERGE (r)-[:COLLECTED_IN]->(l)
    """, has_loc, "COLLECTED_IN rels")

# PART_OF
has_bp = [r for r in sample_meta_rows if r.get("bioproject_id")]
if has_bp:
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (r:SRARun     {run_id:        row.sample_id})
        MATCH (p:BioProject {bioproject_id: row.bioproject_id})
        MERGE (r)-[:PART_OF]->(p)
    """, has_bp, "PART_OF rels")

# PASO 5: Propiedades TB-Profiler en SRARun
log("\n" + "=" * 60)
log("PASO 5: Propiedades TB-Profiler")

if sample_tbp_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (r:SRARun {run_id: row.sample_id})
        SET r.lineage            = row.lineage,
            r.sub_lineage        = row.sub_lineage,
            r.drtype             = row.drtype,
            r.is_mdr             = row.is_mdr,
            r.is_xdr             = row.is_xdr,
            r.is_mtb             = row.is_mtb,
            r.median_depth       = CASE WHEN row.median_depth <> ''    THEN toFloat(row.median_depth)    ELSE null END,
            r.pct_mapped         = CASE WHEN row.pct_mapped <> ''      THEN toFloat(row.pct_mapped)      ELSE null END,
            r.qc_pass            = row.qc_pass,
            r.qc_warnings        = row.qc_warnings,
            r.fail_reasons       = row.fail_reasons,
            r.num_dr_variants    = CASE WHEN row.num_dr_variants <> '' THEN toInteger(row.num_dr_variants) ELSE null END,
            r.tb_profiler_version= row.tb_profiler_version,
            r.db_version         = row.db_version
    """, sample_tbp_rows, "SRARun TB-Profiler props")

#PASO 6: Relaciones TB-Profiler
log("\n" + "=" * 60)
log("PASO 6: Relaciones TB-Profiler")

if belongs_to_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (r:SRARun  {run_id:     row.sample_id})
        MATCH (l:Lineage {lineage_id: row.lineage_id})
        MERGE (r)-[:BELONGS_TO]->(l)
    """, belongs_to_rows, "BELONGS_TO rels")

if detected_in_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (r:SRARun    {run_id:       row.sample_id})
        MATCH (t:TimePoint {timepoint_id: row.timepoint_id})
        MERGE (r)-[:DETECTED_IN]->(t)
    """, detected_in_rows, "DETECTED_IN rels")

if in_cluster_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (r:SRARun  {run_id:     row.sample_id})
        MATCH (c:Cluster {cluster_id: row.cluster_id})
        MERGE (r)-[:IN_CLUSTER]->(c)
    """, in_cluster_rows, "IN_CLUSTER rels")

drug_rows = read_csv("neo4j_nodes_drug.csv")
if drug_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (d:Drug {name: row.drug})
        SET d.drug_class = row.drug_class
    """, drug_rows, "Drug nodes")

mut_rows = read_csv("neo4j_nodes_mutation.csv")
if mut_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (m:Mutation {mutation_id: row.mutation_id})
        SET m.gene           = row.gene,
            m.aa_change      = row.aa_change,
            m.nt_change      = row.nt_change,
            m.variant_type   = row.variant_type,
            m.genome_pos     = CASE WHEN row.genome_pos <> '' THEN toInteger(row.genome_pos) ELSE null END,
            m.confidence     = row.confidence,
            m.who_confidence = row.who_confidence,
            m.variant_class  = row.variant_class,
            m.drug           = row.drug
    """, mut_rows, "Mutation nodes")

res_rows = read_csv("neo4j_rel_resistant_to.csv")
if res_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (r:SRARun {run_id: row.sample_id})
        MATCH (d:Drug   {name:   row.drug})
        MERGE (r)-[rel:RESISTANT_TO]->(d)
        SET rel.confidence     = row.confidence,
            rel.who_confidence = row.who_confidence
    """, res_rows, "RESISTANT_TO rels")

hasmut_rows = read_csv("neo4j_rel_has_mutation.csv")
if hasmut_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (r:SRARun   {run_id:      row.sample_id})
        MATCH (m:Mutation {mutation_id: row.mutation_id})
        MERGE (r)-[rel:HAS_MUTATION]->(m)
        SET rel.allele_freq   = CASE WHEN row.allele_freq   <> '' THEN toFloat(row.allele_freq)     ELSE null END,
            rel.variant_depth = CASE WHEN row.variant_depth <> '' THEN toInteger(row.variant_depth) ELSE null END,
            rel.drug          = row.drug,
            rel.variant_class = row.variant_class
    """, hasmut_rows, "HAS_MUTATION rels")

if mut_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (m:Mutation {mutation_id: row.mutation_id})
        MATCH (d:Drug     {name:        row.drug})
        MERGE (m)-[r:CONFERS_RESISTANCE]->(d)
        SET r.confidence     = row.confidence,
            r.who_confidence = row.who_confidence
    """, mut_rows, "CONFERS_RESISTANCE rels")

linked_rows = read_csv("neo4j_rel_linked_to.csv")
if linked_rows:
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (a:SRARun {run_id: row.sample_a})
        MATCH (b:SRARun {run_id: row.sample_b})
        MERGE (a)-[rel:LINKED_TO]->(b)
        SET rel.snp_dist = CASE WHEN row.snp_dist <> '' THEN toInteger(row.snp_dist) ELSE null END
    """, linked_rows, "LINKED_TO rels")

# PASO 7: Recalcular conteos agregados
log("\n" + "=" * 60)
log("PASO 7: Recalculando conteos agregados")

with driver.session() as session:
    session.run("""
        MATCH (l:Lineage)
        OPTIONAL MATCH (s:SRARun)-[:BELONGS_TO]->(l)
        WITH l, count(s) AS cnt
        SET l.sample_count = cnt
    """)
    log("  Lineage.sample_count actualizado ")

    session.run("""
        MATCH (t:TimePoint)
        OPTIONAL MATCH (s:SRARun)-[:DETECTED_IN]->(t)
        WITH t,
             count(s) AS total,
             sum(CASE WHEN s.is_mdr = 'Yes' THEN 1 ELSE 0 END) AS mdr_cnt
        SET t.sample_count = total,
            t.mdr_count    = mdr_cnt,
            t.mdr_rate     = CASE WHEN total > 0
                             THEN round(toFloat(mdr_cnt)/total*100, 1)
                             ELSE 0.0 END
    """)
    log("  TimePoint conteos actualizados ✅")

    session.run("""
        MATCH (c:Cluster)
        OPTIONAL MATCH (s:SRARun)-[:IN_CLUSTER]->(c)
        WITH c, count(s) AS cnt
        SET c.size = cnt
    """)
    log("  Cluster.size actualizado ")

# PASO 8: Verificación final
log("\n" + "=" * 60)
log("PASO 8: Conteos en Neo4j tras la actualización")

node_labels = ["SRARun","BioSample","Host","Location","BioProject",
               "Lineage","TimePoint","Cluster","Drug","Mutation"]
rel_types   = ["HAS_RUN","FROM_HOST","COLLECTED_IN","PART_OF",
               "BELONGS_TO","DETECTED_IN","IN_CLUSTER",
               "RESISTANT_TO","HAS_MUTATION","CONFERS_RESISTANCE","LINKED_TO"]

with driver.session() as s:
    log(f"\n  {'NODO':<25} {'TOTAL':>6}")
    log(f"  {'-'*25} {'-'*6}")
    for label in node_labels:
        n = s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]
        log(f"  {label:<25} {n:>6}")

    log(f"\n  {'RELACIÓN':<25} {'TOTAL':>6}")
    log(f"  {'-'*25} {'-'*6}")
    for rel in rel_types:
        n = s.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c").single()["c"]
        log(f"  {rel:<25} {n:>6}")

driver.close()
log("\n Carga incremental completada.")
