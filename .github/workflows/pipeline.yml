#!/usr/bin/env python3
"""
Step 4 - Load the CSV files from neo4j_export/ into Neo4j.

  1. Metadata nodes (Location, BioProject, BioSample, Host) and base SRARun nodes
  2. Lineage and TimePoint nodes
  3. Similarity groups (Cluster nodes, replaced on every run)
  4. Metadata relationships (HAS_RUN, FROM_HOST, COLLECTED_IN, PART_OF)
  5. TB-Profiler properties on SRARun nodes, and failed runs
  6. TB-Profiler relationships (lineage, time, groups, drugs, mutations, links)
  7. Recalculate aggregated counts (QC-passed genomes only)
  8. Print node and relationship totals

Usage: python pipeline/04_load_neo4j.py
Requires the NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD environment variables.
"""

import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase

# --- Configuration ---
NEO4J_URI  = os.environ.get("NEO4J_URI")
NEO4J_USER = os.environ.get("NEO4J_USER") or os.environ.get("NEO4J_USERNAME")
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD")

METADATA_CSV     = Path.home() / "metadata_cleaned.csv"
NEO4J_EXPORT_DIR = Path.home() / "neo4j_export"
NEW_RUNS_FILE    = Path.home() / "new_runs.txt"
FAILED_FILE      = Path.home() / "failed_samples.csv"
LOG_FILE         = Path.home() / "load_neo4j_update.log"
BATCH_SIZE       = 500     # rows per UNWIND transaction

LINEAGE_DESC = {
    "lineage1": "Indo-Oceanic (L1)",
    "lineage2": "East-Asian / Beijing (L2)",
    "lineage3": "East-African-Indian (L3)",
    "lineage4": "Euro-American (L4)",
    "lineage5": "West-African 1 (L5)",
    "lineage6": "West-African 2 (L6)",
    "lineage7": "Ethiopian (L7)",
    "lineage8": "Lineage 8 (L8)",
    "lineage9": "Lineage 9 (L9)",
    # Animal-adapted MTBC lineages (TB-Profiler naming)
    "La1"     : "M. bovis (La1, incl. BCG)",
    "La2"     : "M. caprae (La2)",
    "La3"     : "M. orygis (La3)",
    "mixed"   : "Mixed infection (more than one lineage detected)",
    "QC_Failed": "QC Failed - low coverage",
}

NODE_LABELS = ["SRARun", "BioSample", "Host", "Location", "BioProject",
               "Lineage", "TimePoint", "Cluster", "Drug", "Mutation"]
REL_TYPES   = ["HAS_RUN", "FROM_HOST", "COLLECTED_IN", "PART_OF",
               "BELONGS_TO", "DETECTED_IN", "IN_CLUSTER",
               "RESISTANT_TO", "HAS_MUTATION", "CONFERS_RESISTANCE", "LINKED_TO"]


# --- Helpers ---
def log(msg):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def step(title):
    log("\n" + "=" * 60)
    log(title)


def read_csv(filename):
    path = NEO4J_EXPORT_DIR / filename
    if not path.exists():
        log(f"  Not found: {filename} - skipped")
        return []
    df = pd.read_csv(path, dtype=str).fillna("")
    log(f"  {filename:<45} {len(df):>6} rows")
    return df.to_dict("records")


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def run_batch(session_factory, query, rows, label):
    """Run an UNWIND query over rows in batches of BATCH_SIZE."""
    total    = len(rows)
    inserted = 0
    for batch in chunks(rows, BATCH_SIZE):
        with session_factory() as session:
            session.run(query, {"rows": batch})
        inserted += len(batch)
        print(f"    {label}: {inserted}/{total} ({inserted / total * 100:.0f}%)",
              end="\r", flush=True)
    print()
    log(f"  {label:<42} {inserted:>6} records")


def parse_year(date_str):
    """Collection year from an NCBI collection_date ('2019', '2019-05-02').
    Date ranges such as '2013/2016' return None: the real year is unknown,
    so these samples are excluded from yearly statistics (no TimePoint)."""
    if not date_str or date_str.lower() in ("not collected", "missing", "na", "n/a", ""):
        return None
    years = re.findall(r"\b(?:19|20)\d{2}\b", date_str)
    if len(set(years)) != 1:
        return None
    return int(years[0])


def top_level(lineage):
    """'lineage4.1.2' -> 'lineage4'; mixed calls ('lineage2;lineage4') -> 'mixed'."""
    return "mixed" if ";" in lineage else lineage.split(".")[0]


# --- Main ---
def main():
    log("=" * 60)
    log("INCREMENTAL LOAD INTO NEO4J")
    log(f"URI: {NEO4J_URI}")

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        driver.verify_connectivity()
        log("Connected to Neo4j")
    except Exception as e:
        log(f"ERROR connecting to Neo4j: {e}")
        sys.exit(1)

    sf = driver.session  # session factory used by run_batch

    new_runs = set()
    if NEW_RUNS_FILE.exists():
        new_runs = {r.strip() for r in NEW_RUNS_FILE.read_text().splitlines() if r.strip()}
    log(f"New runs to load: {len(new_runs)}")

    # Metadata: one row per run (the most complete row when a run is duplicated)
    log("\nLoading metadata CSV...")
    df_meta_all = pd.read_csv(METADATA_CSV, dtype=str).fillna("")
    with_run    = df_meta_all[df_meta_all["Run"] != ""]
    df_meta = (with_run.copy()
               .assign(_c=(with_run != "").sum(axis=1))
               .sort_values("_c", ascending=False)
               .drop_duplicates(subset="Run")
               .drop(columns="_c")
               .reset_index(drop=True))
    df_meta_new = df_meta[df_meta["Run"].isin(new_runs)].copy()
    log(f"  New runs in metadata: {len(df_meta_new)}")

    log("\nReading CSVs from neo4j_export/...")
    sample_tbp_rows = read_csv("neo4j_nodes_sample.csv")
    df_tbp = pd.DataFrame(sample_tbp_rows) if sample_tbp_rows else pd.DataFrame()

    date_lookup = (df_meta.set_index("Run")["collection_date"].fillna("").to_dict()
                   if "collection_date" in df_meta.columns else {})

    # Step 1: Metadata nodes
    step("STEP 1: Metadata nodes")

    location_rows, bioproject_rows, biosample_rows, host_rows = [], [], [], []
    sample_meta_rows = []
    seen_locations, seen_bioprojects = set(), set()

    for _, row in df_meta_new.iterrows():
        run   = row.get("Run", "")
        state = row.get("state", "")
        bp    = row.get("BioProject_y", "") or row.get("BioProject_x", "") or row.get("BioProject", "")
        bs_id = row.get("BioSampleID", "")
        geo   = row.get("geo_loc_name", "")

        if state and state not in seen_locations:
            try:
                lat = float(row.get("lat", "")) if row.get("lat", "") else None
                lon = float(row.get("lon", "")) if row.get("lon", "") else None
            except ValueError:
                lat = lon = None
            location_rows.append({
                "state": state, "country": geo.split(":")[0].strip() if geo else "Mexico",
                "lat": lat, "lon": lon,
            })
            seen_locations.add(state)

        if bp and bp not in seen_bioprojects:
            bioproject_rows.append({"bioproject_id": bp, "study_id": row.get("SRAStudy", "")})
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
                // Keep existing state coordinates; only fill them if missing
                l.lat     = coalesce(l.lat, toFloat(row.lat)),
                l.lon     = coalesce(l.lon, toFloat(row.lon))
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

    # Base SRARun nodes with read counts (spots)
    srarun_base = [{"run_id": r["sample_id"], "spots": r.get("spots", "0")}
                   for r in sample_meta_rows]
    if srarun_base:
        run_batch(sf, """
            UNWIND $rows AS row
            MERGE (s:SRARun {run_id: row.run_id})
            SET s.spots    = CASE WHEN row.spots <> '' THEN toInteger(row.spots) ELSE 0 END,
                s.has_data = CASE WHEN row.spots <> '0' THEN 'Yes' ELSE 'No' END
        """, srarun_base, "SRARun base nodes")

    # Step 2: Lineage and TimePoint nodes
    step("STEP 2: Lineage and TimePoint")

    lineage_ids      = {}     # ordered set (dict keys) of lineages seen
    belongs_to_rows  = []
    detected_in_rows = []

    if not df_tbp.empty:
        for _, row in df_tbp.iterrows():
            lin = row.get("lineage", "")
            sid = row.get("sample_id", "")
            if lin and lin != "QC_Failed":
                lineage_ids[lin] = None
                belongs_to_rows.append({"sample_id": sid, "lineage_id": lin})

            year = parse_year(date_lookup.get(sid, ""))
            if year:
                detected_in_rows.append({"sample_id": sid, "timepoint_id": str(year), "year": year})

    lineage_rows = [{"lineage_id" : lin,
                     "top_level"  : top_level(lin),
                     "description": LINEAGE_DESC.get(lin, LINEAGE_DESC.get(top_level(lin), ""))}
                    for lin in lineage_ids]
    if lineage_rows:
        run_batch(sf, """
            UNWIND $rows AS row
            MERGE (l:Lineage {lineage_id: row.lineage_id})
            SET l.top_level   = row.top_level,
                l.description = row.description
        """, lineage_rows, "Lineage nodes")

    tp_rows = [{"timepoint_id": tid, "year": yr}
               for tid, yr in {r["timepoint_id"]: r["year"] for r in detected_in_rows}.items()]
    if tp_rows:
        run_batch(sf, """
            UNWIND $rows AS row
            MERGE (t:TimePoint {timepoint_id: row.timepoint_id})
            SET t.year = toInteger(row.year)
        """, tp_rows, "TimePoint nodes")

    # Step 3: Similarity groups
    # Groups are recalculated from ALL samples on every run, so the previous
    # Cluster nodes and IN_CLUSTER relationships are replaced.
    step("STEP 3: Similarity groups (Cluster)")

    cluster_rows_csv = read_csv("resistance_region_clusters.csv")
    cluster_info = {r["cluster_id"]: r for r in cluster_rows_csv
                    if r.get("cluster_id", "") not in ("", "singleton")}

    if cluster_rows_csv:
        with driver.session() as session:
            session.run("MATCH (c:Cluster) DETACH DELETE c")
        log("  Previous groups removed")

    if cluster_info:
        cn_rows = [{"cluster_id": cid, "size": r.get("cluster_size", "1"),
                    "method": r.get("method", ""), "snp_threshold": r.get("snp_threshold", "")}
                   for cid, r in cluster_info.items()]
        run_batch(sf, """
            UNWIND $rows AS row
            MERGE (c:Cluster {cluster_id: row.cluster_id})
            SET c.size          = toInteger(row.size),
                c.method        = row.method,
                c.snp_threshold = toInteger(row.snp_threshold)
        """, cn_rows, "Cluster nodes")

    in_cluster_rows = [{"sample_id": r["sample_id"], "cluster_id": r["cluster_id"]}
                       for r in cluster_rows_csv if r.get("cluster_id", "") != "singleton"]

    # Step 4: Metadata relationships
    step("STEP 4: Metadata relationships")

    has_biosample = [r for r in sample_meta_rows if r.get("biosample_id")]
    if has_biosample:
        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (b:BioSample {biosample_id: row.biosample_id})
            MATCH (r:SRARun    {run_id:       row.run_id})
            MERGE (b)-[:HAS_RUN]->(r)
        """, [{"biosample_id": r["biosample_id"], "run_id": r["sample_id"]} for r in has_biosample],
            "HAS_RUN rels")

        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (r:SRARun {run_id:   row.sample_id})
            MATCH (h:Host   {host_id:  row.biosample_id})
            MERGE (r)-[:FROM_HOST]->(h)
        """, [{"sample_id": r["sample_id"], "biosample_id": r["biosample_id"]} for r in has_biosample],
            "FROM_HOST rels")

    has_loc = [r for r in sample_meta_rows if r.get("state")]
    if has_loc:
        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (r:SRARun   {run_id: row.sample_id})
            MATCH (l:Location {state:  row.state})
            MERGE (r)-[:COLLECTED_IN]->(l)
        """, has_loc, "COLLECTED_IN rels")

    has_bp = [r for r in sample_meta_rows if r.get("bioproject_id")]
    if has_bp:
        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (r:SRARun     {run_id:        row.sample_id})
            MATCH (p:BioProject {bioproject_id: row.bioproject_id})
            MERGE (r)-[:PART_OF]->(p)
        """, has_bp, "PART_OF rels")

    # Step 5: TB-Profiler properties on SRARun nodes
    step("STEP 5: TB-Profiler properties")

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
                r.is_rr              = row.is_rr,
                r.species            = row.species,
                r.mixed_infection    = row.mixed_infection,
                r.median_depth       = CASE WHEN row.median_depth <> ''    THEN toFloat(row.median_depth)    ELSE null END,
                r.pct_mapped         = CASE WHEN row.pct_mapped <> ''      THEN toFloat(row.pct_mapped)      ELSE null END,
                r.qc_pass            = row.qc_pass,
                r.qc_warnings        = row.qc_warnings,
                r.fail_reasons       = row.fail_reasons,
                r.num_dr_variants    = CASE WHEN row.num_dr_variants <> '' THEN toInteger(row.num_dr_variants) ELSE null END,
                r.num_other_variants = CASE WHEN row.num_other_variants <> '' THEN toInteger(row.num_other_variants) ELSE null END,
                r.resistant_drugs    = row.resistant_drugs,
                r.collection_date    = row.collection_date,
                r.isolation_source   = row.isolation_source,
                r.processing_status  = 'ok',
                r.processing_error   = null,
                r.tb_profiler_version= row.tb_profiler_version,
                r.db_version         = row.db_version
        """, sample_tbp_rows, "SRARun TB-Profiler props")

    # Runs where the download or TB-Profiler failed (written by 02_run_tbprofiler.py)
    if FAILED_FILE.exists():
        failed_rows = pd.read_csv(FAILED_FILE, dtype=str).fillna("").to_dict("records")
        if failed_rows:
            run_batch(sf, """
                UNWIND $rows AS row
                MERGE (r:SRARun {run_id: row.run_id})
                SET r.processing_status = 'failed',
                    r.processing_error  = row.error
            """, failed_rows, "SRARun failed runs")

    # Step 6: TB-Profiler relationships
    step("STEP 6: TB-Profiler relationships")

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

    # Only resistance mutations have a drug; rows without one find no Drug and are skipped
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

    # Step 7: Aggregated counts (QC-passed genomes only)
    step("STEP 7: Recalculating aggregated counts")

    with driver.session() as session:
        session.run("""
            MATCH (l:Lineage)
            OPTIONAL MATCH (s:SRARun {qc_pass: 'PASS'})-[:BELONGS_TO]->(l)
            WITH l, count(s) AS cnt
            SET l.sample_count = cnt
        """)
        log("  Lineage.sample_count updated")

        session.run("""
            MATCH (t:TimePoint)
            OPTIONAL MATCH (s:SRARun {qc_pass: 'PASS'})-[:DETECTED_IN]->(t)
            WITH t,
                 count(s) AS total,
                 sum(CASE WHEN s.is_mdr = 'Yes' THEN 1 ELSE 0 END) AS mdr_cnt,
                 sum(CASE WHEN s.is_rr  = 'Yes' THEN 1 ELSE 0 END) AS rr_cnt
            SET t.sample_count = total,
                t.mdr_count    = mdr_cnt,
                t.mdr_rate     = CASE WHEN total > 0
                                 THEN round(toFloat(mdr_cnt)/total*100, 1)
                                 ELSE 0.0 END,
                t.rr_count     = rr_cnt,
                t.rr_rate      = CASE WHEN total > 0
                                 THEN round(toFloat(rr_cnt)/total*100, 1)
                                 ELSE 0.0 END
        """)
        log("  TimePoint counts updated")

        session.run("""
            MATCH (c:Cluster)
            OPTIONAL MATCH (s:SRARun)-[:IN_CLUSTER]->(c)
            WITH c, count(s) AS cnt
            SET c.size = cnt
        """)
        log("  Cluster.size updated")

    # Step 8: Totals
    step("STEP 8: Neo4j totals after the update")

    with driver.session() as session:
        log(f"\n  {'NODE':<25} {'TOTAL':>6}")
        log(f"  {'-' * 25} {'-' * 6}")
        for label in NODE_LABELS:
            n = session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]
            log(f"  {label:<25} {n:>6}")

        log(f"\n  {'RELATIONSHIP':<25} {'TOTAL':>6}")
        log(f"  {'-' * 25} {'-' * 6}")
        for rel in REL_TYPES:
            n = session.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c").single()["c"]
            log(f"  {rel:<25} {n:>6}")

    driver.close()
    log("\nIncremental load completed.")


if __name__ == "__main__":
    main()
