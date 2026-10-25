#!/usr/bin/env python3
"""
Step 3 - Build the CSV files that are loaded into Neo4j.

The graph is centred on BioSample (one node per biological sample). When a
BioSample has more than one SRA run, only the best run is used:
  - among runs that pass QC, the one with the highest target median depth;
  - if none passes QC, the run with the highest depth.
Runs that are not selected are not loaded into Neo4j (their JSONs stay in the
GitHub data release). BioSamples without a usable SRA run (saved by step 1 as a
row with an empty Run) are loaded too, with processing_status = 'no_run'.

  1. Read the TB-Profiler JSON results (new runs + all historical runs)
  2. Select the best run of every BioSample
  3. Build BioSample, SRARun, mutation and drug rows for the BioSamples that have
     a new run (a new run can replace the one selected before)
  4. Save the CSV files to neo4j_export/

Usage: python pipeline/03_build_graph_csvs.py
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

# --- Configuration ---
METADATA_CSV  = Path.home() / "metadata_cleaned.csv"
JSON_CACHE    = Path.home() / "json_cache"
OUTPUT_DIR    = Path.home() / "neo4j_export"
NEW_RUNS_FILE = Path.home() / "new_runs.txt"
FAILED_FILE   = Path.home() / "failed_samples.csv"   # written by 02_run_tbprofiler.py

# QC thresholds: a sample passes if target median depth >= MIN_DEPTH (x)
# and reads mapped >= MIN_PCT_MAPPED (%)
MIN_DEPTH      = 10
MIN_PCT_MAPPED = 90

# Resistance categories from TB-Profiler drtype (WHO 2021 definitions)
RR_TYPES = {"RR-TB", "MDR-TB", "Pre-XDR-TB", "XDR-TB"}   # rifampicin resistant

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

# Metadata columns copied to each BioSample row (CSV column -> output column)
META_COLUMNS = {
    "state": "state", "lat": "lat", "lon": "lon",
    "collection_date": "collection_date", "isolation_source": "isolation_source",
    "host": "host_type", "host_sex": "host_sex", "host_age": "host_age",
    "host_disease": "host_disease", "SRAStudy": "study_id",
}


# --- Helpers ---
def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def qc_values(data):
    qc = data.get("qc", {})
    return qc.get("target_median_depth", 0) or 0, qc.get("percent_reads_mapped", 0) or 0


def passes_qc(data):
    depth, mapped = qc_values(data)
    return depth >= MIN_DEPTH and mapped >= MIN_PCT_MAPPED


def select_best_run(runs, all_data):
    """Best run of a BioSample: the highest-depth run among those that pass QC;
    if none passes, the highest-depth run. Ties are broken by % reads mapped,
    then by run ID so the choice is always the same. None if no run has a result."""
    candidates = [r for r in runs if r in all_data]
    if not candidates:
        return None
    passing = [r for r in candidates if passes_qc(all_data[r])]
    pool = passing or candidates
    return max(pool, key=lambda r: (*qc_values(all_data[r]), r))


def mutation_id(df):
    """gene_ntchange_drug. nt_change is used because aa_change is empty for
    promoter/non-coding variants, which would make different variants share an ID."""
    return (df["gene"].fillna("") + "_" +
            df["nt_change"].fillna("") + "_" +
            df["drug"].fillna("")).str.strip("_")


def build_summary(data):
    """Lineage, resistance profile and QC summary of one TB-Profiler result."""
    depth, mapped = qc_values(data)
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

    # QC failure reasons and warnings
    reasons = []
    if depth < MIN_DEPTH:
        reasons.append(f"low_depth({depth:.1f}x)")
    if mapped < MIN_PCT_MAPPED:
        reasons.append(f"low_mapping({mapped:.1f}%)")
    qc = data.get("qc", {})
    warnings = qc.get("qc_notes", qc.get("notes", []))
    if isinstance(warnings, str):
        warnings = [warnings]

    pipeline_info = data.get("pipeline", {})
    db_version    = pipeline_info.get("db_version", data.get("db_version", "unknown"))

    return {
        "lineage"            : lineage or "QC_Failed",
        "sub_lineage"        : data.get("sub_lineage", "QC_Failed") if qc_pass == "PASS" else "QC_Failed",
        "drtype"             : drtype,
        "is_rr"              : rr,
        "is_mdr"             : mdr,
        "is_xdr"             : xdr,
        "is_mtb"             : is_mtb,
        "species"            : species,
        "mixed_infection"    : "Yes" if ";" in lineage else "No",
        "resistant_drugs"    : "; ".join(sorted(res_drugs)),
        "median_depth"       : round(depth, 1),
        "pct_mapped"         : round(mapped, 1),
        "qc_pass"            : qc_pass,
        "fail_reasons"       : " | ".join(reasons) or "None",
        "qc_warnings"        : " | ".join(warnings) if warnings else "None",
        "num_dr_variants"    : len(data.get("dr_variants", [])),
        "num_other_variants" : len(data.get("other_variants", [])),
        "tb_profiler_version": pipeline_info.get("software_version",
                                                 data.get("software_version", "unknown")),
        "db_version"         : (db_version.get("commit", str(db_version))
                                if isinstance(db_version, dict) else db_version),
    }


def build_mut_rows(biosample_id, run_id, data):
    """One row per variant (and per drug for resistance variants)."""
    rows = []
    depth, mapped = qc_values(data)
    lin = data.get("main_lineage", "")
    sub = data.get("sub_lineage", "")

    def base(var):
        freq = var.get("freq")
        return {
            "biosample_id" : biosample_id,
            "run_id"       : run_id,
            "lineage"      : lin, "sub_lineage": sub,
            "gene"         : var.get("gene_name", ""),
            "genome_pos"   : var.get("pos"),
            "nt_change"    : var.get("nucleotide_change", ""),
            "aa_change"    : var.get("protein_change", ""),
            "variant_type" : var.get("type", ""),
            "allele_freq"  : round(freq, 4) if freq else None,
            "variant_depth": var.get("depth"),
            "sample_depth" : round(depth, 1),
            "pct_mapped"   : round(mapped, 1),
        }

    for var in data.get("dr_variants", []):
        for drug_entry in var.get("drugs", []):
            rows.append({**base(var),
                         "drug"          : drug_entry.get("drug", ""),
                         "confidence"    : drug_entry.get("confidence", ""),
                         "who_confidence": drug_entry.get("who_confidence", ""),
                         "variant_class" : "dr_variant"})

    for var in data.get("other_variants", []):
        rows.append({**base(var),
                     "drug"          : "",
                     "confidence"    : var.get("confidence", ""),
                     "who_confidence": var.get("who_confidence", ""),
                     "variant_class" : "other_variant"})
    return rows


def first_value(series):
    """First non-empty value of a metadata column ('' if there is none)."""
    values = series[series.fillna("").astype(str).str.strip() != ""]
    return values.iloc[0] if len(values) else ""


# --- Main ---
def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    JSON_CACHE.mkdir(exist_ok=True)

    # Step 1: New runs, metadata and TB-Profiler results
    new_runs = set()
    if NEW_RUNS_FILE.exists():
        new_runs = {r.strip() for r in NEW_RUNS_FILE.read_text().splitlines() if r.strip()}
    log(f"New runs to process: {len(new_runs)}")

    # Metadata: one row per run (the most complete row when a run is duplicated).
    # BioSamples with no run row are kept apart: they become BioSample nodes without SRA data.
    df_all  = pd.read_csv(METADATA_CSV, dtype=str).fillna("")
    df_all["BioSampleID"] = df_all["BioSampleID"].str.strip()
    df_meta = df_all[df_all["Run"].str.strip() != ""].copy()
    df_meta["Run"] = df_meta["Run"].str.strip()
    df_meta = (df_meta
               .assign(_c=(df_meta != "").sum(axis=1))
               .sort_values("_c", ascending=False)
               .drop_duplicates(subset="Run")
               .drop(columns="_c"))
    runs_by_biosample = df_meta.groupby("BioSampleID")["Run"].apply(list).to_dict()
    biosample_of_run  = dict(zip(df_meta["Run"], df_meta["BioSampleID"]))
    meta_by_run       = df_meta.set_index("Run")
    no_run_rows       = (df_all[~df_all["BioSampleID"].isin(runs_by_biosample)
                                & (df_all["BioSampleID"] != "")]
                         .drop_duplicates(subset="BioSampleID")
                         .set_index("BioSampleID"))

    # All JSONs (historical + new) are loaded: the best run of a BioSample may be
    # an older one.
    log("Loading JSONs from the local cache...")
    all_json_files = list(JSON_CACHE.glob("*.results.json"))
    log(f"Total JSONs in cache: {len(all_json_files)}")

    all_data, corrupt = {}, []
    for jf in all_json_files:
        run_id = jf.name.replace(".results.json", "")
        # Only runs listed in metadata_cleaned.csv are used (e.g. removed lab-strain
        # runs whose JSONs are still in an older release are ignored)
        if run_id not in biosample_of_run:
            continue
        try:
            with open(jf) as f:
                all_data[run_id] = json.load(f)
        except Exception as e:
            corrupt.append(run_id)
            log(f"  Corrupt: {run_id} - {e}")
    log(f"Valid JSONs: {len(all_data)}")
    if corrupt:
        log(f"Corrupt    : {len(corrupt)}")

    failed_errors = {}
    if FAILED_FILE.exists():
        df_failed = pd.read_csv(FAILED_FILE, dtype=str).fillna("")
        failed_errors = dict(zip(df_failed["run_id"], df_failed["error"]))

    # Step 2: Best run of every BioSample
    best_run = {bs: select_best_run(runs, all_data) for bs, runs in runs_by_biosample.items()}
    multi = {bs: runs for bs, runs in runs_by_biosample.items() if len(runs) > 1}
    log(f"BioSamples: {len(runs_by_biosample)} ({len(multi)} with more than one run)")
    for bs, runs in multi.items():
        log(f"  {bs}: {len(runs)} runs, {sum(r in all_data for r in runs)} with results "
            f"-> selected {best_run[bs]}")

    # BioSamples to (re)build: those with at least one new run, plus every BioSample
    # without a run (only metadata, cheap to rebuild; this also loads new ones)
    affected = sorted({biosample_of_run[r] for r in new_runs if r in biosample_of_run}
                      | set(no_run_rows.index))
    log(f"BioSamples without a run: {len(no_run_rows)}")
    unknown  = new_runs - set(biosample_of_run)
    if unknown:
        log(f"  Warning: {len(unknown)} new runs are not in metadata_cleaned.csv (ignored)")
    log(f"BioSamples to build: {len(affected)}")

    # Step 3: BioSample, SRARun, mutation and drug rows
    log("\n1. Building BioSample nodes and their relationships...")
    biosample_rows, run_rows, mut_rows = [], [], []

    for bs in affected:
        runs = runs_by_biosample.get(bs, [])
        best = best_run.get(bs)
        # Metadata from the selected run (or the most complete row if there is none)
        if best:
            meta_rows = meta_by_run.loc[[best]]
        elif runs:
            meta_rows = meta_by_run.loc[runs]
        else:
            meta_rows = no_run_rows.loc[[bs]]
        row = {"biosample_id"     : bs,
               "selected_run"     : best or "",
               "n_runs"           : len(runs),
               "n_runs_with_result": sum(r in all_data for r in runs)}
        for src, dst in META_COLUMNS.items():
            row[dst] = first_value(meta_rows[src]) if src in meta_rows.columns else ""
        bp_cols = [c for c in ("BioProject_y", "BioProject_x", "BioProject") if c in meta_rows.columns]
        row["bioproject_id"] = next((v for v in (first_value(meta_rows[c]) for c in bp_cols) if v), "")
        geo = first_value(meta_rows["geo_loc_name"]) if "geo_loc_name" in meta_rows.columns else ""
        row["country"] = geo.split(":")[0].strip() if geo else "Mexico"

        if best:
            data = all_data[best]
            row.update(build_summary(data))
            row.update({"processing_status": "ok", "processing_error": ""})
            spots = meta_by_run.at[best, "spots"] if "spots" in meta_by_run.columns else ""
            run_rows.append({"run_id": best, "biosample_id": bs, "spots": spots,
                             "median_depth": row["median_depth"], "pct_mapped": row["pct_mapped"],
                             "qc_pass": row["qc_pass"],
                             "tb_profiler_version": row["tb_profiler_version"],
                             "db_version": row["db_version"]})
            mut_rows.extend(build_mut_rows(bs, best, data))
        elif not runs:
            row.update({"processing_status": "no_run",
                        "processing_error" : "No WGS run with reads in SRA"})
        else:
            spots = (pd.to_numeric(meta_rows["spots"], errors="coerce").fillna(0)
                     if "spots" in meta_rows.columns else pd.Series([0]))
            if (spots > 0).any():
                errors = [failed_errors[r] for r in runs if r in failed_errors]
                row.update({"processing_status": "failed",
                            "processing_error" : errors[0] if errors else "No TB-Profiler result"})
            else:
                row.update({"processing_status": "no_data",
                            "processing_error" : "No reads in SRA (spots = 0)"})
        biosample_rows.append(row)

    node_biosample = pd.DataFrame(biosample_rows)
    # Same columns even when no BioSample in this batch has a TB-Profiler result
    for col in build_summary({}):
        if col not in node_biosample.columns:
            node_biosample[col] = ""
    node_run       = pd.DataFrame(run_rows)
    df_mut         = pd.DataFrame(mut_rows) if mut_rows else pd.DataFrame()
    if not node_biosample.empty:
        status_counts = node_biosample["processing_status"].value_counts().to_dict()
        log(f"  BioSample rows : {len(node_biosample)} {status_counts}")
    log(f"  SRARun rows    : {len(node_run)}")
    log(f"  Mutation rows  : {len(df_mut)}")

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
            ["biosample_id", "gene", "nt_change", "aa_change", "drug",
             "allele_freq", "variant_depth", "variant_class"]].copy()
        rel_has_mut["mutation_id"] = mutation_id(rel_has_mut)

        rel_res = (df_mut[df_mut["drug"] != ""]
                   [["biosample_id", "drug", "confidence", "who_confidence"]].drop_duplicates())
    else:
        node_mut = node_drug = rel_has_mut = rel_res = pd.DataFrame()

    # Step 4: Save CSVs (files from a previous run are removed first, so an
    # empty table never leaves an old file behind)
    log("\n3. Saving CSVs to ~/neo4j_export/...")
    for old in OUTPUT_DIR.glob("*.csv"):
        old.unlink()
    files = {
        "neo4j_nodes_biosample.csv"     : node_biosample,
        "neo4j_nodes_run.csv"           : node_run,
        "neo4j_nodes_mutation.csv"      : node_mut,
        "neo4j_nodes_drug.csv"          : node_drug,
        "neo4j_rel_has_mutation.csv"    : rel_has_mut,
        "neo4j_rel_resistant_to.csv"    : rel_res,
        "mutation_details.csv"          : df_mut,
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
