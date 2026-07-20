#!/usr/bin/env python3
#Generar CSV
  #1. Lee JSONs de los nuevos runs
  #2. Generar nodos y relaciones nuevas
  #3. Resultados en neo4j_export

#Uso: python pipeline/03_generarcsvs

import os, json, glob, subprocess
import pandas as pd
import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from datetime import datetime
from pathlib import Path

# Rutas
METADATA_CSV  = Path.home() / "metadata_cleaned.csv"
JSON_CACHE    = Path.home() / "json_cache"
OUTPUT_DIR    = Path.home() / "neo4j_export"
NEW_RUNS_FILE = Path.home() / "new_runs.txt"
SNP_THRESHOLD = 12

OUTPUT_DIR.mkdir(exist_ok=True)
JSON_CACHE.mkdir(exist_ok=True)


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# 1. Leer runs nuevos
if not NEW_RUNS_FILE.exists() or NEW_RUNS_FILE.stat().st_size == 0:
    log("new_runs.txt vacío. Sin muestras nuevas que procesar.")
    exit(0)

new_runs = {r.strip() for r in NEW_RUNS_FILE.read_text().splitlines() if r.strip()}
log(f"Runs nuevos a procesar: {len(new_runs)}")

# Cargar TODOS los JSONs del cache (histórico y nuevos) necesarios para actualizar clusters/relaciones/nodos
log("Cargando JSONs del cache local...")
all_json_files = list(JSON_CACHE.glob("*.results.json"))
log(f"Total JSONs en cache: {len(all_json_files)}")

all_data  = {}   # todos para clustering
new_data  = {}   # solo nuevos para nodos/relaciones

corrupt = []
for jf in all_json_files:
    sid = jf.name.replace(".results.json", "")
    try:
        with open(jf) as f:
            d = json.load(f)
        all_data[sid] = d
        if sid in new_runs:
            new_data[sid] = d
    except Exception as e:
        corrupt.append(sid)
        log(f"  Corrupto: {sid} — {e}")

log(f"JSONs válidos totales : {len(all_data)}")
log(f"JSONs nuevos válidos  : {len(new_data)}")
if corrupt:
    log(f"Corruptos             : {len(corrupt)}")

# Construir fila de resumen para un sample
def build_summary_row(sid, data):
    qc      = data.get("qc", {})
    depth   = qc.get("target_median_depth", 0)
    mapped  = qc.get("percent_reads_mapped", 0)
    qc_pass = "PASS" if (depth >= 10 and mapped >= 90) else "FAIL"

    res_drugs = set()
    for v in data.get("dr_variants", []):
        for d in v.get("drugs", []):
            if d.get("drug"):
                res_drugs.add(d["drug"].lower())

    mdr = "Yes" if {"isoniazid", "rifampicin"}.issubset(res_drugs) else "No"
    xdr = "Yes" if (mdr == "Yes"
                    and res_drugs & {"moxifloxacin", "levofloxacin"}
                    and res_drugs & {"bedaquiline", "linezolid"}) else "No"

    lineage_val = data.get("main_lineage", "") if qc_pass == "PASS" else "QC_Failed"
    is_mtb      = "No" if (qc_pass == "PASS" and lineage_val.startswith("La")) else "Yes"

    return {
        "sample_id"   : sid,
        "lineage"     : lineage_val or "QC_Failed",
        "sub_lineage" : data.get("sub_lineage", "QC_Failed") if qc_pass == "PASS" else "QC_Failed",
        "drtype"      : data.get("drtype", "Unknown") if qc_pass == "PASS" else "Low_coverage",
        "is_mdr"      : mdr,
        "is_xdr"      : xdr,
        "is_mtb"      : is_mtb,
        "median_depth": round(depth, 1),
        "pct_mapped"  : round(mapped, 1),
        "qc_pass"     : qc_pass,
    }


def build_qc_row(sid, data):
    qc      = data.get("qc", {})
    depth   = qc.get("target_median_depth", 0)
    mapped  = qc.get("percent_reads_mapped", 0)
    reasons = []
    if depth  < 10: reasons.append(f"low_depth({depth:.1f}x)")
    if mapped < 90: reasons.append(f"low_mapping({mapped:.1f}%)")
    warnings = qc.get("qc_notes", qc.get("notes", []))
    if isinstance(warnings, str):
        warnings = [warnings]
    return {
        "sample_id"               : sid,
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


def build_mut_rows(sid, data):
    rows   = []
    qc     = data.get("qc", {})
    depth  = qc.get("target_median_depth", 0)
    mapped = qc.get("percent_reads_mapped", 0)
    lin    = data.get("main_lineage", "")
    sub    = data.get("sub_lineage", "")

    for var in data.get("dr_variants", []):
        gene      = var.get("gene_name", "")
        nt_change = var.get("nucleotide_change", "")
        aa_change = var.get("protein_change", "")
        freq      = var.get("freq")
        for drug_entry in var.get("drugs", []):
            rows.append({
                "sample_id"    : sid,
                "lineage"      : lin, "sub_lineage": sub,
                "gene"         : gene,
                "genome_pos"   : var.get("pos"),
                "nt_change"    : nt_change,
                "aa_change"    : aa_change,
                "variant_type" : var.get("type", ""),
                "allele_freq"  : round(freq, 4) if freq else None,
                "variant_depth": var.get("depth"),
                "drug"         : drug_entry.get("drug", ""),
                "confidence"   : drug_entry.get("confidence", ""),
                "who_confidence": drug_entry.get("who_confidence", ""),
                "variant_class": "dr_variant",
                "sample_depth" : round(depth, 1),
                "pct_mapped"   : round(mapped, 1),
            })

    for var in data.get("other_variants", []):
        freq = var.get("freq")
        rows.append({
            "sample_id"    : sid,
            "lineage"      : lin, "sub_lineage": sub,
            "gene"         : var.get("gene_name", ""),
            "genome_pos"   : var.get("pos"),
            "nt_change"    : var.get("nucleotide_change", ""),
            "aa_change"    : var.get("protein_change", ""),
            "variant_type" : var.get("type", ""),
            "allele_freq"  : round(freq, 4) if freq else None,
            "variant_depth": var.get("depth"),
            "drug"         : "",
            "confidence"   : var.get("confidence", ""),
            "who_confidence": var.get("who_confidence", ""),
            "variant_class": "other_variant",
            "sample_depth" : round(depth, 1),
            "pct_mapped"   : round(mapped, 1),
        })
    return rows



# PASO 1: Nodos y relaciones de los runs NUEVOS
log("\n1. Generando nodos/relaciones para runs nuevos...")

summary_rows = [build_summary_row(sid, d) for sid, d in new_data.items()]
qc_rows      = [build_qc_row(sid, d)      for sid, d in new_data.items()]
mut_rows     = []
for sid, d in new_data.items():
    mut_rows.extend(build_mut_rows(sid, d))

df_summary = pd.DataFrame(summary_rows)
df_qc      = pd.DataFrame(qc_rows)
df_mut     = pd.DataFrame(mut_rows) if mut_rows else pd.DataFrame()

log(f"  Resumen muestras nuevas : {len(df_summary)}")
log(f"  Mutaciones nuevas       : {len(df_mut)}")

# Nodos Sample (merge summary + qc)
if not df_summary.empty and not df_qc.empty:
    node_sample = df_summary.merge(
        df_qc[["sample_id", "qc_pass", "fail_reasons", "num_dr_variants",
                "num_other_variants", "qc_warnings", "tb_profiler_version", "db_version"]],
        on="sample_id", how="left"
    )
else:
    node_sample = df_summary.copy()

# Integrar metadata geográfica
try:
    df_meta = pd.read_csv(METADATA_CSV, dtype=str).fillna("")
    df_meta = (df_meta
               .assign(_c=df_meta.notna().sum(axis=1))
               .sort_values("_c", ascending=False)
               .drop_duplicates(subset="Run")
               .drop(columns="_c"))
    keep = [c for c in ["Run","state","lat","lon","collection_date",
                         "BioProject_y","isolation_source"] if c in df_meta.columns]
    df_meta2 = df_meta[keep].rename(columns={"Run": "sample_id"})
    # Filtrar solo los nuevos
    df_meta2 = df_meta2[df_meta2["sample_id"].isin(new_runs)]
    node_sample = node_sample.merge(df_meta2, on="sample_id", how="left")
    log(f"  Metadata integrada para {len(df_meta2)} runs nuevos")
except Exception as e:
    log(f"  Advertencia integrando metadata: {e}")

# Nodos Mutation y Drug (solo nuevos)
if not df_mut.empty:
    node_mut = df_mut[["gene","nt_change","aa_change","variant_type",
                        "genome_pos","drug","confidence","who_confidence",
                        "variant_class"]].drop_duplicates()
    node_mut["mutation_id"] = (
        node_mut["gene"].fillna("") + "_" +
        node_mut["aa_change"].fillna("") + "_" +
        node_mut["drug"].fillna("")
    ).str.strip("_")

    node_drug = pd.DataFrame({"drug": df_mut["drug"].dropna().unique()})
    drug_class_map = {
        "isoniazid":"1st_line", "rifampicin":"1st_line",
        "ethambutol":"1st_line", "pyrazinamide":"1st_line",
        "streptomycin":"1st_line_injectable",
        "moxifloxacin":"fluoroquinolone", "levofloxacin":"fluoroquinolone",
        "bedaquiline":"group_A", "linezolid":"group_A",
        "pretomanid":"group_A", "clofazimine":"group_A",
        "delamanid":"group_B",
        "amikacin":"2nd_line_injectable", "kanamycin":"2nd_line_injectable",
        "capreomycin":"2nd_line_injectable",
    }
    node_drug["drug_class"] = node_drug["drug"].map(drug_class_map).fillna("other")

    rel_has_mut = df_mut[df_mut["variant_class"]=="dr_variant"][
        ["sample_id","gene","aa_change","drug","allele_freq","variant_depth","variant_class"]
    ].copy()
    rel_has_mut["mutation_id"] = (
        rel_has_mut["gene"].fillna("") + "_" +
        rel_has_mut["aa_change"].fillna("") + "_" +
        rel_has_mut["drug"].fillna("")
    ).str.strip("_")

    rel_res = df_mut[["sample_id","drug","confidence","who_confidence"]].drop_duplicates()
else:
    node_mut    = pd.DataFrame()
    node_drug   = pd.DataFrame()
    rel_has_mut = pd.DataFrame()
    rel_res     = pd.DataFrame()



# PASO 2: Recalcular clusters con TODOS los JSONs
log("\n2. Recalculando clusters SNP con todos los JSONs...")

# Construir matriz de variantes con todos los datos
all_mut_rows = []
for sid, data in all_data.items():
    for var in data.get("dr_variants", []) + data.get("other_variants", []):
        gene   = var.get("gene_name", "")
        change = var.get("nucleotide_change", "") or var.get("protein_change", "")
        if gene and change:
            all_mut_rows.append({"sample": sid, "variant_key": f"{gene}_{change}"})

cluster_rows  = []
pairwise_rows = []

if all_mut_rows:
    df_var = pd.DataFrame(all_mut_rows)
    df_var["present"] = 1
    matrix = (df_var
              .pivot_table(index="sample", columns="variant_key",
                           values="present", fill_value=0)
              .astype(np.int8))

    samples_in_matrix = matrix.index.tolist()
    arr = matrix.values
    n   = len(samples_in_matrix)
    log(f"  Matriz: {n} muestras × {matrix.shape[1]} variantes")

    dist_matrix = np.zeros((n, n), dtype=np.int32)
    for i in range(n):
        diff = (arr[i] != arr[i+1:]).sum(axis=1)
        dist_matrix[i, i+1:] = diff
        dist_matrix[i+1:, i] = diff

    # Guardar pares cercanos (solo los nuevos como sample_a para eficiencia)
    new_indices = [i for i, s in enumerate(samples_in_matrix) if s in new_runs]
    for i in new_indices:
        for j in range(n):
            if i == j:
                continue
            d = int(dist_matrix[i, j])
            if d <= SNP_THRESHOLD * 5:
                pairwise_rows.append({
                    "sample_a": samples_in_matrix[i],
                    "sample_b": samples_in_matrix[j],
                    "snp_dist": d,
                    "linked"  : "Yes" if d <= SNP_THRESHOLD else "No",
                })

    # Clustering
    condensed     = squareform(dist_matrix)
    Z             = linkage(condensed, method="single")
    cluster_labels = fcluster(Z, t=SNP_THRESHOLD, criterion="distance")

    label_map = {}
    for sid, lbl in zip(samples_in_matrix, cluster_labels):
        label_map.setdefault(lbl, []).append(sid)

    clustered = set()
    cid_counter = 1
    for lbl, members in label_map.items():
        if len(members) == 1:
            continue
        cid = f"C{cid_counter:04d}"
        cid_counter += 1
        for sid in members:
            cluster_rows.append({
                "sample_id"    : sid,
                "cluster_id"   : cid,
                "cluster_size" : len(members),
                "snp_threshold": SNP_THRESHOLD,
            })
            clustered.add(sid)

    for sid in all_data:
        if sid not in clustered:
            cluster_rows.append({
                "sample_id"    : sid,
                "cluster_id"   : "singleton",
                "cluster_size" : 1,
                "snp_threshold": SNP_THRESHOLD,
            })

    non_singleton = [r for r in cluster_rows if r["cluster_id"] != "singleton"]
    log(f"  Muestras en clusters: {len(non_singleton)}")
    log(f"  Clústeres distintos : {len(set(r['cluster_id'] for r in non_singleton))}")
    log(f"  Singletons          : {len(cluster_rows) - len(non_singleton)}")
else:
    log("  Sin variantes disponibles — todas marcadas como singleton")
    for sid in all_data:
        cluster_rows.append({
            "sample_id": sid, "cluster_id": "singleton",
            "cluster_size": 1, "snp_threshold": SNP_THRESHOLD,
        })

df_clusters = pd.DataFrame(cluster_rows)
df_pairwise = pd.DataFrame(pairwise_rows)

# Agregar cluster a node_sample de los nuevos
if not df_clusters.empty and not node_sample.empty:
    df_clust_new = df_clusters[df_clusters["sample_id"].isin(new_runs)]
    node_sample = node_sample.merge(
        df_clust_new[["sample_id", "cluster_id", "cluster_size"]],
        on="sample_id", how="left"
    )



# PASO 3: Guardar CSVs
log("\n3. Guardando CSVs en ~/neo4j_export/...")

# Se guardan los archivos con datos de los runs nuevos
files = {
    "neo4j_nodes_sample.csv"        : node_sample,
    "neo4j_nodes_mutation.csv"      : node_mut,
    "neo4j_nodes_drug.csv"          : node_drug,
    "neo4j_rel_has_mutation.csv"    : rel_has_mut,
    "neo4j_rel_resistant_to.csv"    : rel_res,
    "mutation_details.csv"          : df_mut,
    # Clusters completos (recalculados con todos los datos)
    "transmission_clusters.csv"     : df_clusters,
    "pairwise_snp_distances.csv"    : df_pairwise,
}

for fname, df in files.items():
    if df is not None and not df.empty:
        path = OUTPUT_DIR / fname
        df.to_csv(path, index=False)
        log(f"  {fname:<42} {len(df):>6} filas")
    else:
        log(f"  {fname:<42} (vacío, omitido)")

log("\nCSVs listos para cargar a Neo4j.")
