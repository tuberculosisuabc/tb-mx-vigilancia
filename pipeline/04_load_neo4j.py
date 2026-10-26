#!/usr/bin/env python3
"""
Step 4 - Load the CSV files from neo4j_export/ into Neo4j.

The graph is centred on BioSample: lineage, resistance, QC, location, date and
mutations hang from the BioSample node. Each BioSample has at most one SRARun
node, the run selected by 03_build_graph_csvs.py.

  1. Remove the previous data of the BioSamples being rebuilt (their SRARun node
     and relationships), so a better run can replace the one selected before
  2. BioSample nodes with their TB-Profiler and metadata properties
  3. SRARun nodes (selected run) and HAS_RUN
  4. Metadata nodes and relationships (Location, BioProject, Host)
  5. Lineage and TimePoint nodes and relationships
  6. Drugs and mutations
  7. Recalculate aggregated counts (QC-passed BioSamples only)
  8. Print node and relationship totals

Usage: python pipeline/04_load_neo4j.py
Requires the NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD environment variables.
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase

# --- Configuration ---
NEO4J_URI  = os.environ.get("NEO4J_URI")
NEO4J_USER = os.environ.get("NEO4J_USER") or os.environ.get("NEO4J_USERNAME")
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD")

NEO4J_EXPORT_DIR = Path.home() / "neo4j_export"
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

NODE_LABELS = ["BioSample", "SRARun", "Host", "Location", "BioProject",
               "Lineage", "TimePoint", "Drug", "Mutation"]
REL_TYPES   = ["HAS_RUN", "FROM_HOST", "COLLECTED_IN", "PART_OF",
               "BELONGS_TO", "DETECTED_IN",
               "RESISTANT_TO", "HAS_MUTATION", "CONFERS_RESISTANCE"]


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
    """CSV rows as dicts; empty cells become None (null in Neo4j)."""
    path = NEO4J_EXPORT_DIR / filename
    if not path.exists():
        log(f"  Not found: {filename} - skipped")
        return []
    df = pd.read_csv(path, dtype=str)
    df = df.astype(object).where(df.notna() & (df != ""), None)
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

    # Unique keys. Each constraint also creates an index, so the MATCH/MERGE lookups
    # below do not scan every node (important for ~30,000 HAS_MUTATION rows).
    with driver.session() as session:
        for label, key in [("BioSample", "biosample_id"), ("SRARun", "run_id"),
                           ("Host", "host_id"), ("Location", "state"),
                           ("BioProject", "bioproject_id"), ("Lineage", "lineage_id"),
                           ("TimePoint", "timepoint_id"), ("Drug", "name"),
                           ("Mutation", "mutation_id")]:
            session.run(f"CREATE CONSTRAINT {label.lower()}_{key} IF NOT EXISTS "
                        f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE")
    log("Constraints and indexes ready")

    log("\nReading CSVs from neo4j_export/...")
    biosample_rows = read_csv("neo4j_nodes_biosample.csv")
    if not biosample_rows:
        log("No BioSamples to load. Nothing to do.")
        driver.close()
        return
    run_rows = read_csv("neo4j_nodes_run.csv")
    ids      = [{"biosample_id": r["biosample_id"]} for r in biosample_rows]
    ok_rows  = [r for r in biosample_rows if r.get("processing_status") == "ok"]

    # Step 1: Remove previous data of the BioSamples being rebuilt
    step("STEP 1: Removing previous data of rebuilt BioSamples")
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (b:BioSample {biosample_id: row.biosample_id})
        OPTIONAL MATCH (b)-[:HAS_RUN]->(s:SRARun)
        DETACH DELETE s
    """, ids, "Previous SRARun nodes removed")
    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (b:BioSample {biosample_id: row.biosample_id})-[r]-()
        DELETE r
    """, ids, "Previous relationships removed")

    # Step 2: BioSample nodes: biological sample, metadata and final classification.
    # Sequencing quality and analysis versions belong to SRARun (step 3); the main lineage
    # and the resistant drugs are relationships (BELONGS_TO, RESISTANT_TO), not properties.
    # Every property is written on every load, so values from a replaced run never stay
    # behind (empty values become null).
    step("STEP 2: BioSample nodes")
    run_batch(sf, """
        UNWIND $rows AS row
        MERGE (b:BioSample {biosample_id: row.biosample_id})
        SET b.selected_run        = row.selected_run,
            b.n_runs              = toInteger(row.n_runs),
            b.n_runs_with_result  = toInteger(row.n_runs_with_result),
            b.processing_status   = row.processing_status,
            b.processing_error    = row.processing_error,
            b.collection_date     = row.collection_date,
            b.isolation_source    = row.isolation_source,
            b.sub_lineage         = row.sub_lineage,
            b.drtype              = row.drtype,
            b.is_rr               = row.is_rr,
            b.is_mdr              = row.is_mdr,
            b.is_xdr              = row.is_xdr,
            b.is_mtb              = row.is_mtb,
            b.species             = row.species,
            b.mixed_infection     = row.mixed_infection,
            // qc_pass is also on SRARun; kept here because every statistic filters on it
            b.qc_pass             = row.qc_pass
    """, biosample_rows, "BioSample nodes")

    # Step 3: Selected SRARun nodes
    step("STEP 3: SRARun nodes (selected run of each BioSample)")
    if run_rows:
        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (b:BioSample {biosample_id: row.biosample_id})
            MERGE (s:SRARun {run_id: row.run_id})
            SET s.spots               = toInteger(toFloat(row.spots)),
                s.median_depth        = toFloat(row.median_depth),
                s.pct_mapped          = toFloat(row.pct_mapped),
                s.qc_pass             = row.qc_pass,
                s.fail_reasons        = row.fail_reasons,
                s.qc_warnings         = row.qc_warnings,
                s.num_dr_variants     = toInteger(row.num_dr_variants),
                s.num_other_variants  = toInteger(row.num_other_variants),
                s.tb_profiler_version = row.tb_profiler_version,
                s.db_version          = row.db_version
            MERGE (b)-[:HAS_RUN]->(s)
        """, run_rows, "SRARun nodes + HAS_RUN")

    # Step 4: Metadata nodes and relationships
    step("STEP 4: Metadata (Location, BioProject, Host)")

    has_loc = [r for r in biosample_rows if r.get("state")]
    if has_loc:
        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (b:BioSample {biosample_id: row.biosample_id})
            MERGE (l:Location {state: row.state})
            SET l.country = coalesce(l.country, row.country),
                // Keep existing state coordinates; only fill them if missing
                l.lat     = coalesce(l.lat, toFloat(row.lat)),
                l.lon     = coalesce(l.lon, toFloat(row.lon))
            MERGE (b)-[:COLLECTED_IN]->(l)
        """, has_loc, "Location + COLLECTED_IN")

    has_bp = [r for r in biosample_rows if r.get("bioproject_id")]
    if has_bp:
        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (b:BioSample {biosample_id: row.biosample_id})
            MERGE (p:BioProject {bioproject_id: row.bioproject_id})
            SET p.study_id = coalesce(row.study_id, p.study_id)
            MERGE (b)-[:PART_OF]->(p)
        """, has_bp, "BioProject + PART_OF")

    run_batch(sf, """
        UNWIND $rows AS row
        MATCH (b:BioSample {biosample_id: row.biosample_id})
        MERGE (h:Host {host_id: row.biosample_id})
        SET h.host_type    = row.host_type,
            h.host_sex     = row.host_sex,
            h.host_age     = row.host_age,
            h.host_disease = row.host_disease
        MERGE (b)-[:FROM_HOST]->(h)
    """, biosample_rows, "Host + FROM_HOST")

    # Step 5: Lineage and TimePoint (only BioSamples with a TB-Profiler result)
    step("STEP 5: Lineage and TimePoint")

    belongs_to_rows = [{"biosample_id": r["biosample_id"], "lineage_id": r["lineage"],
                        "top_level": top_level(r["lineage"]),
                        "description": LINEAGE_DESC.get(r["lineage"],
                                                        LINEAGE_DESC.get(top_level(r["lineage"]), ""))}
                       for r in ok_rows if r.get("lineage") and r["lineage"] != "QC_Failed"]
    if belongs_to_rows:
        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (b:BioSample {biosample_id: row.biosample_id})
            MERGE (l:Lineage {lineage_id: row.lineage_id})
            SET l.top_level   = row.top_level,
                l.description = row.description
            MERGE (b)-[:BELONGS_TO]->(l)
        """, belongs_to_rows, "Lineage + BELONGS_TO")

    detected_in_rows = []
    for r in ok_rows:
        year = parse_year(r.get("collection_date") or "")
        if year:
            detected_in_rows.append({"biosample_id": r["biosample_id"],
                                     "timepoint_id": str(year), "year": year})
    if detected_in_rows:
        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (b:BioSample {biosample_id: row.biosample_id})
            MERGE (t:TimePoint {timepoint_id: row.timepoint_id})
            SET t.year = toInteger(row.year)
            MERGE (b)-[:DETECTED_IN]->(t)
        """, detected_in_rows, "TimePoint + DETECTED_IN")

    # Step 6: Drugs and mutations
    step("STEP 6: Drugs and mutations")

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
                m.aa_change      = coalesce(row.aa_change, ''),
                m.nt_change      = coalesce(row.nt_change, ''),
                m.variant_type   = row.variant_type,
                m.genome_pos     = toInteger(toFloat(row.genome_pos)),
                m.variant_class  = row.variant_class
        """, mut_rows, "Mutation nodes")

    res_rows = read_csv("neo4j_rel_resistant_to.csv")
    if res_rows:
        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (b:BioSample {biosample_id: row.biosample_id})
            MATCH (d:Drug      {name:         row.drug})
            MERGE (b)-[:RESISTANT_TO]->(d)
        """, res_rows, "RESISTANT_TO rels")

    hasmut_rows = read_csv("neo4j_rel_has_mutation.csv")
    if hasmut_rows:
        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (b:BioSample {biosample_id: row.biosample_id})
            MATCH (m:Mutation  {mutation_id:  row.mutation_id})
            MERGE (b)-[rel:HAS_MUTATION]->(m)
            SET rel.allele_freq   = toFloat(row.allele_freq),
                rel.variant_depth = toInteger(toFloat(row.variant_depth))
        """, hasmut_rows, "HAS_MUTATION rels")

    # Which drugs each resistance mutation affects, with the catalogue confidence
    confers_rows = read_csv("neo4j_rel_confers_resistance.csv")
    if confers_rows:
        run_batch(sf, """
            UNWIND $rows AS row
            MATCH (m:Mutation {mutation_id: row.mutation_id})
            MATCH (d:Drug     {name:        row.drug})
            MERGE (m)-[r:CONFERS_RESISTANCE]->(d)
            SET r.confidence     = row.confidence,
                r.who_confidence = row.who_confidence
        """, confers_rows, "CONFERS_RESISTANCE rels")

    # Step 7: Aggregated counts (QC-passed M. tuberculosis BioSamples only; M. bovis
    # genomes are kept in the graph but excluded from every statistic)
    step("STEP 7: Recalculating aggregated counts")

    with driver.session() as session:
        session.run("""
            MATCH (l:Lineage)
            OPTIONAL MATCH (b:BioSample {qc_pass: 'PASS', is_mtb: 'Yes'})-[:BELONGS_TO]->(l)
            WITH l, count(b) AS cnt
            SET l.sample_count = cnt
        """)
        log("  Lineage.sample_count updated")

        session.run("""
            MATCH (t:TimePoint)
            OPTIONAL MATCH (b:BioSample {qc_pass: 'PASS', is_mtb: 'Yes'})-[:DETECTED_IN]->(t)
            WITH t,
                 count(b) AS total,
                 sum(CASE WHEN b.is_mdr = 'Yes' THEN 1 ELSE 0 END) AS mdr_cnt,
                 sum(CASE WHEN b.is_rr  = 'Yes' THEN 1 ELSE 0 END) AS rr_cnt
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

        # SRARun nodes that are not the selected run of any BioSample (left over
        # from the old run-centred model). Remove them with a full reload.
        orphans = session.run("""
            MATCH (s:SRARun) WHERE NOT ()-[:HAS_RUN]->(s) RETURN count(s) AS c
        """).single()["c"]
        if orphans:
            log(f"\n  WARNING: {orphans} SRARun nodes are not linked to a BioSample. "
                "Run 'Recargar datos históricos en Neo4j' with the database wiped.")

    driver.close()
    log("\nIncremental load completed.")


if __name__ == "__main__":
    main()
