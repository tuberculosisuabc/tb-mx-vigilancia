#!/usr/bin/env python3
"""
Step 3 - Build the CSV files that are loaded into Neo4j.

  1. Read the TB-Profiler JSON results (new runs + all historical runs)
  2. Build sample, mutation and drug nodes and their relationships for the new runs
  3. Recalculate resistance-region similarity groups with ALL QC-passed runs
  4. Save the CSV files to neo4j_export/

Usage: python pipeline/03_build_graph_csvs.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

# --- Configuration ---
METADATA_CSV  = Path.home() / "metadata_cleaned.csv"
JSON_CACHE    = Path.home() / "json_cache"
OUTPUT_DIR    = Path.home() / "neo4j_export"
NEW_RUNS_FILE = Path.home() / "new_runs.txt"

# QC thresholds: a sample passes if target median depth >= MIN_DEPTH (x)
# and reads mapped >= MIN_PCT_MAPPED (%)
MIN_DEPTH      = 10
MIN_PCT_MAPPED = 90

# Resistance categories from TB-Profiler drtype (WHO 2021 definitions)
RR_TYPES = {"RR-TB", "MDR-TB", "Pre-XDR-TB", "XDR-TB"}   # rifampicin resistant

# Similarity groups: maximum pairwise SNP distance (single linkage)
SNP_THRESHOLD  = 12
CLUSTER_METHOD = "resistance_loci_snp_distance"

# WHO 2022 drug classification (Consolidated guidelines, Module 4: Treatment).
# First-line drugs for drug-susceptible TB, then WHO groups A/B/C for
# MDR/RR-TB regimens. Kanamycin and capreomycin are no longer recommended.
# Pretomanid is not part of groups A-C (used in the BPaL/BPaLM regimens).
DRUG_CLASSES = {
    "isoniazid": "first_line", "rifampicin": "first_line",
    "ethambutol": "first_line", "pyrazinamide": "first_line",
    "levofloxacin": "group_A", "moxifloxacin": "group_A",
    "bedaquiline": "group_A", "linezolid": "group_A",
    "clofazimine": "group_B", "cycloserine": "group_B", "terizidone": "group_B",
    "delamanid": "group_C", "amikacin": "group_C", "streptomycin": "group_C",
    "ethionamide": "group_C", "prothionamide": "group_C",
    "para-aminosalicylic_acid": "group_C",
    "imipenem": "group_C", "meropenem": "group_C",
    "kanamycin": "not_recommended", "capreomycin": "not_recommended",
    "pretomanid": "bpal_regimen",
}


# --- Helpers ---
def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def passes_qc(data):
    qc = data.get("qc", {})
    return (qc.get("target_median_depth", 0) >= MIN_DEPTH
            and qc.get("percent_reads_mapped", 0) >= MIN_PCT_MAPPED)


def mutation_id(df):
    """gene_ntchange_drug. nt_change is used because aa_change is empty for
    promoter/non-coding variants, which would make different variants share an ID."""
    return (df["gene"].fillna("") + "_" +
            df["nt_change"].fillna("") + "_" +
            df["drug"].fillna("")).str.strip("_")


def build_summary_row(run_id, data):
    """Lineage, resistance profile and QC summary for one run (SRARun node)."""
    qc      = data.get("qc", {})
    depth   = qc.get("target_median_depth", 0)
    mapped  = qc.get("percent_reads_mapped", 0)
    qc_pass = "PASS" if (depth >= MIN_DEPTH and mapped >= MIN_PCT_MAPPED) else "FAIL"

    res_drugs = set()
    for v in data.get("dr_variants", []):
        for d in v.get("drugs", []):
            if d.get("drug"):
                res_drugs.add(d["drug"].lower())

    # Resistance flags are only assigned to genomes that pass QC ("Unknown" otherwise;
    # not "NA", which pandas reads back as an empty value).
    # They follow TB-Profiler's drtype, so flags and drtype always agree:
    #   is_mdr = resistant to isoniazid AND rifampicin (strict MDR)
    #   is_rr  = resistant to rifampicin (WHO "MDR/RR-TB" reporting group)
    #   is_xdr = drtype XDR-TB (MDR/RR-TB + fluoroquinolone + bedaquiline/linezolid)
    if qc_pass == "PASS":
        drtype = data.get("drtype", "Unknown")
        rr     = "Yes" if drtype in RR_TYPES else "No"
        mdr    = "Yes" if (rr == "Yes" and "isoniazid" in res_drugs) else "No"
        xdr    = "Yes" if drtype == "XDR-TB" else "No"
    else:
        drtype, rr, mdr, xdr = "Low_coverage", "Unknown", "Unknown", "Unknown"
        res_drugs = set()

    lineage = data.get("main_lineage", "") if qc_pass == "PASS" else "QC_Failed"
    # Species from TB-Profiler's lineage call, e.g. "M.bovis" for La1 (incl. BCG).
    # La lineages belong to the M. tuberculosis complex but are not M. tuberculosis.
    lineage_calls = data.get("lineage") or [{}]
    family  = lineage_calls[0].get("family", "") if qc_pass == "PASS" else ""
    is_mtb  = "No" if (qc_pass == "PASS" and lineage.startswith("La")) else "Yes"
    species = (family if family.startswith("M.") else "M.tuberculosis") if qc_pass == "PASS" else ""

    return {
        "sample_id"      : run_id,
        "lineage"        : lineage or "QC_Failed",
        "sub_lineage"    : data.get("sub_lineage", "QC_Failed") if qc_pass == "PASS" else "QC_Failed",
        "drtype"         : drtype,
        "is_rr"          : rr,
        "is_mdr"         : mdr,
        "is_xdr"         : xdr,
        "is_mtb"         : is_mtb,
        "species"        : species,
        "mixed_infection": "Yes" if ";" in lineage else "No",
        "resistant_drugs": "; ".join(sorted(res_drugs)),
        "median_depth"   : round(depth, 1),
        "pct_mapped"     : round(mapped, 1),
        "qc_pass"        : qc_pass,
    }


def build_qc_row(run_id, data):
    """QC details for one run: failure reasons, warnings and software versions."""
    qc      = data.get("qc", {})
    depth   = qc.get("target_median_depth", 0)
    mapped  = qc.get("percent_reads_mapped", 0)
    reasons = []
    if depth < MIN_DEPTH:
        reasons.append(f"low_depth({depth:.1f}x)")
    if mapped < MIN_PCT_MAPPED:
        reasons.append(f"low_mapping({mapped:.1f}%)")
    warnings = qc.get("qc_notes", qc.get("notes", []))
    if isinstance(warnings, str):
        warnings = [warnings]
    return {
        "sample_id"               : run_id,
        "qc_pass"                 : "FAIL" if reasons else "PASS",
        "fail_reasons"            : " | ".join(reasons) or "None",
        "median_depth"            : round(depth, 1),
        "pct_reads_mapped"        : round(mapped, 1),
        "num_reads_mapped"        : qc.get("num_reads_mapped"),
        "pct_target_bases_covered": qc.get("target_pct_coverage", qc.get("pct_bases_covered")),
        "num_dr_variants"         : len(data.get("dr_variants", [])),
        "num_other_variants"      : len(data.get("other_variants", [])),
        "qc_warnings"             : " | ".join(warnings) if warnings else "None",
        "tb_profiler_version"     : data.get("pipeline", {}).get("software_version",
                                     data.get("software_version", "unknown")),
        "db_version"              : data.get("pipeline", {}).get("db_version",
                                     data.get("db_version", "unknown")),
    }


def build_mut_rows(run_id, data):
    """One row per variant (and per drug for resistance variants)."""
    rows   = []
    qc     = data.get("qc", {})
    depth  = qc.get("target_median_depth", 0)
    mapped = qc.get("percent_reads_mapped", 0)
    lin    = data.get("main_lineage", "")
    sub    = data.get("sub_lineage", "")

    for var in data.get("dr_variants", []):
        freq = var.get("freq")
        for drug_entry in var.get("drugs", []):
            rows.append({
                "sample_id"     : run_id,
                "lineage"       : lin, "sub_lineage": sub,
                "gene"          : var.get("gene_name", ""),
                "genome_pos"    : var.get("pos"),
                "nt_change"     : var.get("nucleotide_change", ""),
                "aa_change"     : var.get("protein_change", ""),
                "variant_type"  : var.get("type", ""),
                "allele_freq"   : round(freq, 4) if freq else None,
                "variant_depth" : var.get("depth"),
                "drug"          : drug_entry.get("drug", ""),
                "confidence"    : drug_entry.get("confidence", ""),
                "who_confidence": drug_entry.get("who_confidence", ""),
                "variant_class" : "dr_variant",
                "sample_depth"  : round(depth, 1),
                "pct_mapped"    : round(mapped, 1),
            })

    for var in data.get("other_variants", []):
        freq = var.get("freq")
        rows.append({
            "sample_id"     : run_id,
            "lineage"       : lin, "sub_lineage": sub,
            "gene"          : var.get("gene_name", ""),
            "genome_pos"    : var.get("pos"),
            "nt_change"     : var.get("nucleotide_change", ""),
            "aa_change"     : var.get("protein_change", ""),
            "variant_type"  : var.get("type", ""),
            "allele_freq"   : round(freq, 4) if freq else None,
            "variant_depth" : var.get("depth"),
            "drug"          : "",
            "confidence"    : var.get("confidence", ""),
            "who_confidence": var.get("who_confidence", ""),
            "variant_class" : "other_variant",
            "sample_depth"  : round(depth, 1),
            "pct_mapped"    : round(mapped, 1),
        })
    return rows


def similarity_row(run_id, cluster_id, size):
    return {"sample_id": run_id, "cluster_id": cluster_id, "cluster_size": size,
            "snp_threshold": SNP_THRESHOLD, "method": CLUSTER_METHOD}


# --- Main ---
def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    JSON_CACHE.mkdir(exist_ok=True)

    # Step 1: Read new runs and TB-Profiler results
    if not NEW_RUNS_FILE.exists() or NEW_RUNS_FILE.stat().st_size == 0:
        log("new_runs.txt is empty. No new samples to process.")
        sys.exit(0)

    new_runs = {r.strip() for r in NEW_RUNS_FILE.read_text().splitlines() if r.strip()}
    log(f"New runs to process: {len(new_runs)}")

    # All JSONs (historical + new) are loaded: similarity groups use every run,
    # nodes and relationships are only built for the new ones.
    log("Loading JSONs from the local cache...")
    all_json_files = list(JSON_CACHE.glob("*.results.json"))
    log(f"Total JSONs in cache: {len(all_json_files)}")

    # Only runs listed in metadata_cleaned.csv are used (e.g. removed lab-strain runs
    # whose JSONs are still in an older release are ignored)
    known_runs = set(pd.read_csv(METADATA_CSV, dtype=str, usecols=["Run"])["Run"].dropna().str.strip())

    all_data, new_data, corrupt = {}, {}, []
    for jf in all_json_files:
        run_id = jf.name.replace(".results.json", "")
        if run_id not in known_runs:
            continue
        try:
            with open(jf) as f:
                d = json.load(f)
            all_data[run_id] = d
            if run_id in new_runs:
                new_data[run_id] = d
        except Exception as e:
            corrupt.append(run_id)
            log(f"  Corrupt: {run_id} - {e}")

    log(f"Valid JSONs (all) : {len(all_data)}")
    log(f"Valid JSONs (new) : {len(new_data)}")
    if corrupt:
        log(f"Corrupt           : {len(corrupt)}")

    # Step 2: Nodes and relationships for the new runs
    log("\n1. Building nodes and relationships for new runs...")
    summary_rows = [build_summary_row(run_id, d) for run_id, d in new_data.items()]
    qc_rows      = [build_qc_row(run_id, d)      for run_id, d in new_data.items()]
    mut_rows     = [row for run_id, d in new_data.items() for row in build_mut_rows(run_id, d)]

    df_summary = pd.DataFrame(summary_rows)
    df_qc      = pd.DataFrame(qc_rows)
    df_mut     = pd.DataFrame(mut_rows) if mut_rows else pd.DataFrame()
    log(f"  New sample summaries : {len(df_summary)}")
    log(f"  New mutation rows    : {len(df_mut)}")

    # SRARun nodes: summary + QC details (qc_pass comes from the summary)
    if not df_summary.empty and not df_qc.empty:
        node_sample = df_summary.merge(
            df_qc[["sample_id", "fail_reasons", "num_dr_variants",
                   "num_other_variants", "qc_warnings", "tb_profiler_version", "db_version"]],
            on="sample_id", how="left")
    else:
        node_sample = df_summary.copy()

    # Add location, date and isolation source from the metadata
    try:
        df_meta = pd.read_csv(METADATA_CSV, dtype=str).fillna("")
        df_meta = (df_meta
                   .assign(_c=df_meta.notna().sum(axis=1))
                   .sort_values("_c", ascending=False)
                   .drop_duplicates(subset="Run")
                   .drop(columns="_c"))
        keep = [c for c in ["Run", "state", "lat", "lon", "collection_date",
                            "BioProject_y", "isolation_source"] if c in df_meta.columns]
        df_meta_new = df_meta[keep].rename(columns={"Run": "sample_id"})
        df_meta_new = df_meta_new[df_meta_new["sample_id"].isin(new_runs)]
        node_sample = node_sample.merge(df_meta_new, on="sample_id", how="left")
        log(f"  Metadata added for {len(df_meta_new)} new runs")
    except Exception as e:
        log(f"  Warning while adding metadata: {e}")

    # Mutation and Drug nodes, HAS_MUTATION and RESISTANT_TO relationships
    if not df_mut.empty:
        node_mut = df_mut[["gene", "nt_change", "aa_change", "variant_type",
                           "genome_pos", "drug", "confidence", "who_confidence",
                           "variant_class"]].drop_duplicates()
        node_mut["mutation_id"] = mutation_id(node_mut)

        # other_variants have no drug (""), so only real drug names become Drug nodes
        drug_names = df_mut["drug"].dropna()
        node_drug  = pd.DataFrame({"drug": drug_names[drug_names != ""].unique()})
        node_drug["drug_class"] = node_drug["drug"].map(DRUG_CLASSES).fillna("other")

        rel_has_mut = df_mut[df_mut["variant_class"] == "dr_variant"][
            ["sample_id", "gene", "nt_change", "aa_change", "drug",
             "allele_freq", "variant_depth", "variant_class"]].copy()
        rel_has_mut["mutation_id"] = mutation_id(rel_has_mut)

        rel_res = (df_mut[df_mut["drug"] != ""]
                   [["sample_id", "drug", "confidence", "who_confidence"]].drop_duplicates())
    else:
        node_mut = node_drug = rel_has_mut = rel_res = pd.DataFrame()

    # Step 3: Resistance-region similarity groups, recalculated with all runs
    #
    # Method note: distances count differences in the variants TB-Profiler reports
    # (dr_variants + other_variants), which only cover the loci in its resistance
    # database (~70 genes), NOT the whole genome. Groups therefore reflect similar
    # resistance-region genotypes and must NOT be interpreted as transmission
    # clusters, which require genome-wide SNP distances.
    # Only genomes that pass QC are included.
    log("\n2. Recalculating similarity groups (resistance regions)...")

    qc_pass_ids  = [run_id for run_id, data in all_data.items() if passes_qc(data)]
    variant_rows = []
    for run_id in qc_pass_ids:
        data = all_data[run_id]
        for var in data.get("dr_variants", []) + data.get("other_variants", []):
            gene   = var.get("gene_name", "")
            change = var.get("nucleotide_change", "") or var.get("protein_change", "")
            if gene and change:
                variant_rows.append({"sample": run_id, "variant_key": f"{gene}_{change}"})

    cluster_rows  = []
    pairwise_rows = []

    if variant_rows:
        # Presence/absence matrix: runs x variants
        df_var = pd.DataFrame(variant_rows)
        df_var["present"] = 1
        matrix = (df_var
                  .pivot_table(index="sample", columns="variant_key",
                               values="present", fill_value=0)
                  .astype(np.int8))
        samples = matrix.index.tolist()
        arr = matrix.values
        n   = len(samples)
        log(f"  Matrix: {n} samples x {matrix.shape[1]} variants")

        dist_matrix = np.zeros((n, n), dtype=np.int32)
        for i in range(n):
            diff = (arr[i] != arr[i + 1:]).sum(axis=1)
            dist_matrix[i, i + 1:] = diff
            dist_matrix[i + 1:, i] = diff

        # Pairwise distances involving new runs (each pair once, up to 5x the threshold)
        new_indices = [i for i, s in enumerate(samples) if s in new_runs]
        seen_pairs  = set()
        for i in new_indices:
            for j in range(n):
                if i == j:
                    continue
                a, b = sorted((samples[i], samples[j]))
                if (a, b) in seen_pairs:
                    continue
                seen_pairs.add((a, b))
                d = int(dist_matrix[i, j])
                if d <= SNP_THRESHOLD * 5:
                    pairwise_rows.append({
                        "sample_a": a,
                        "sample_b": b,
                        "snp_dist": d,
                        "linked"  : "Yes" if d <= SNP_THRESHOLD else "No",
                    })

        # Single-linkage grouping at SNP_THRESHOLD
        labels = fcluster(linkage(squareform(dist_matrix), method="single"),
                          t=SNP_THRESHOLD, criterion="distance")
        members_by_label = {}
        for run_id, label in zip(samples, labels):
            members_by_label.setdefault(label, []).append(run_id)

        grouped = set()
        for members in members_by_label.values():
            if len(members) == 1:
                continue
            # Group ID = first member run ID in alphabetical order. Unlike a counter
            # (C0001, C0002...), it stays the same between runs unless the group changes.
            cluster_id = f"CL_{min(members)}"
            for run_id in members:
                cluster_rows.append(similarity_row(run_id, cluster_id, len(members)))
                grouped.add(run_id)

        for run_id in qc_pass_ids:
            if run_id not in grouped:
                cluster_rows.append(similarity_row(run_id, "singleton", 1))

        in_groups = [r for r in cluster_rows if r["cluster_id"] != "singleton"]
        log(f"  Samples in groups : {len(in_groups)}")
        log(f"  Distinct groups   : {len({r['cluster_id'] for r in in_groups})}")
        log(f"  Singletons        : {len(cluster_rows) - len(in_groups)}")
    else:
        log("  No variants available - all samples marked as singletons")
        for run_id in qc_pass_ids:
            cluster_rows.append(similarity_row(run_id, "singleton", 1))

    df_clusters = pd.DataFrame(cluster_rows)
    df_pairwise = pd.DataFrame(pairwise_rows)
    df_linked   = (df_pairwise[df_pairwise["linked"] == "Yes"][["sample_a", "sample_b", "snp_dist"]]
                   if not df_pairwise.empty else pd.DataFrame())

    # Add the group of each new run to its SRARun node
    if not df_clusters.empty and not node_sample.empty:
        node_sample = node_sample.merge(
            df_clusters[df_clusters["sample_id"].isin(new_runs)]
            [["sample_id", "cluster_id", "cluster_size"]],
            on="sample_id", how="left")

    # Step 4: Save CSVs
    log("\n3. Saving CSVs to ~/neo4j_export/...")
    files = {
        "neo4j_nodes_sample.csv"        : node_sample,
        "neo4j_nodes_mutation.csv"      : node_mut,
        "neo4j_nodes_drug.csv"          : node_drug,
        "neo4j_rel_has_mutation.csv"    : rel_has_mut,
        "neo4j_rel_resistant_to.csv"    : rel_res,
        "mutation_details.csv"          : df_mut,
        "resistance_region_clusters.csv": df_clusters,
        "pairwise_snp_distances.csv"    : df_pairwise,
        "neo4j_rel_linked_to.csv"       : df_linked,
    }
    for fname, df in files.items():
        if df is not None and not df.empty:
            df.to_csv(OUTPUT_DIR / fname, index=False)
            log(f"  {fname:<42} {len(df):>6} rows")
        else:
            log(f"  {fname:<42} (empty, skipped)")

    log("\nCSVs ready to load into Neo4j.")


if __name__ == "__main__":
    main()
