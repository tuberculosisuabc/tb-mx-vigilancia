#!/usr/bin/env python3
"""
Step 1 - Fetch new M. tuberculosis samples from NCBI.

  1. Load the existing metadata (metadata_cleaned.csv)
  2. Search BioSample for M. tuberculosis isolates from Mexico
  3. Download the XML of BioSamples not yet in the metadata
  4. Search SRA and download run info for those BioSamples
  5. Merge BioSample + SRA, keep WGS runs with data, drop laboratory strains
  6. Assign the state and its coordinates from geo_loc_name
  7. Append the new rows to metadata_cleaned.csv
  8. Write the run IDs to process to new_runs.txt

Usage: python pipeline/01_fetch_ncbi.py
"""

import sys
import time
import difflib
import unicodedata
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path

import pandas as pd
from Bio import Entrez

# Configuration
Entrez.email  = "daniela.santana@uabc.edu.mx"
METADATA_CSV  = Path.home() / "metadata_cleaned.csv"
NEW_RUNS_FILE = Path.home() / "new_runs.txt"
PENDING_FILE  = Path.home() / "pending_runs.txt"   # runs left for the next run (a number)
RETMAX = 2000
BATCH_SIZE    = 200      # BioSamples per efetch request
MAX_RUNS = 25 #Max samples to process to stay under github limit of  6 hours

BIOSAMPLE_QUERY = (
    '"Mycobacterium tuberculosis"[Organism] '
    'AND ("Mexico"[Organism] OR "Mexico"[All Fields]) '
    'NOT ("Mycobacterium tuberculosis variant bovis"[Organism] OR "mice"[All fields])'
)

# Representative coordinates for each state (used for the map)
STATE_COORDS = {
    "Aguascalientes":     (21.8818, -102.2916),
    "Baja California":    (30.8406, -115.2838),
    "Baja California Sur":(26.0444, -111.6661),
    "Campeche":           (19.8301,  -90.5349),
    "Chiapas":            (16.7569,  -93.1292),
    "Chihuahua":          (28.6353, -106.0889),
    "Ciudad de Mexico":   (19.4326,  -99.1332),
    "Coahuila":           (27.0587, -101.7068),
    "Colima":             (19.2452, -103.7241),
    "Durango":            (24.0277, -104.6532),
    "Guanajuato":         (21.0190, -101.2574),
    "Guerrero":           (17.4392, -100.0000),
    "Hidalgo":            (20.0911,  -98.7624),
    "Jalisco":            (20.6595, -103.3494),
    "Estado de Mexico":   (19.3588,  -99.8237),
    "Michoacan":          (19.5665, -101.7068),
    "Morelos":            (18.6813,  -99.1013),
    "Nayarit":            (21.7514, -104.8455),
    "Nuevo Leon":         (25.5922,  -99.9962),
    "Oaxaca":             (17.0732,  -96.7266),
    "Puebla":             (19.0414,  -98.2063),
    "Queretaro":          (20.5888, -100.3899),
    "Quintana Roo":       (19.1817,  -88.4791),
    "San Luis Potosi":    (22.1565, -100.9855),
    "Sinaloa":            (25.1721, -107.4795),
    "Sonora":             (29.2972, -110.3309),
    "Tabasco":            (17.8409,  -92.6189),
    "Tamaulipas":         (24.2669,  -98.8363),
    "Tlaxcala":           (19.3182,  -98.2375),
    "Veracruz":           (19.1738,  -96.1342),
    "Yucatan":            (20.7099,  -89.0943),
    "Zacatecas":          (22.7709, -102.5832),
}

# Spellings found in NCBI records that differ from the official state name
STATE_ALIASES = {
    "cdmx": "Ciudad de Mexico",
    "mexico city": "Ciudad de Mexico",
    "iztapalapa": "Ciudad de Mexico",
    "edo mx": "Estado de Mexico",
    "edomx": "Estado de Mexico",
    "monterrey": "Nuevo Leon",
    "xalapa": "Veracruz",
    "veracurz": "Veracruz",
    "acapulco guerrereo": "Guerrero",
    "atoyac de alvarez guerrero": "Guerrero",
}

# Columns used later by the pipeline: never dropped as "similar" duplicates
KEY_COLUMNS = {"BioSampleID", "Run", "geo_loc_name", "collection_date",
               "isolation_source", "host", "spots", "BioProject_x", "BioProject_y"}


# --- Helpers ---
def log(msg):
    print(msg, flush=True)


def normalize(text):
    """'Nuevo León ' -> 'nuevo leon'"""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


STATE_LOOKUP = {normalize(s): s for s in STATE_COORDS} | STATE_ALIASES


def extract_state(geo_loc_name):
    """'Mexico: Xalapa, Veracruz' -> ('Veracruz', lat, lon).
    Returns ('', None, None) if no state is given or it isn't recognised."""
    if pd.isna(geo_loc_name) or ":" not in str(geo_loc_name):
        return "", None, None
    for part in str(geo_loc_name).split(":", 1)[1].split(","):
        state = STATE_LOOKUP.get(normalize(part))
        if state:
            return state, *STATE_COORDS[state]
    return "", None, None


def drop_similar_columns(df, threshold=0.8):
    """Drop near-duplicate columns created by the BioSample + SRA merge
    (similar names and >95% identical values). Key columns are always kept."""
    cols, drop = df.columns.tolist(), set()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            c1, c2 = cols[i], cols[j]
            if c1 in drop or c2 in drop:
                continue
            if c1 in KEY_COLUMNS and c2 in KEY_COLUMNS:
                continue
            if difflib.SequenceMatcher(None, c1.lower(), c2.lower()).ratio() < threshold:
                continue
            s1, s2 = df[c1], df[c2]
            if not (pd.api.types.is_numeric_dtype(s1) and pd.api.types.is_numeric_dtype(s2)):
                match_frac = ((s1 == s2) | (s1.isna() & s2.isna())).sum() / len(df)
                if match_frac > 0.95:
                    if c1 in KEY_COLUMNS:
                        drop.add(c2)
                    elif c2 in KEY_COLUMNS:
                        drop.add(c1)
                    else:
                        drop.add(c1 if s1.isna().sum() >= s2.isna().sum() else c2)
    return df.drop(columns=list(drop))


def parse_biosample(bs):
    """Flatten one <BioSample> XML element into a dict."""
    sample = {
        "BioSampleID":      bs.attrib.get("accession"),
        "publication_date": bs.attrib.get("publication_date"),
        "submission_date":  bs.attrib.get("submission_date"),
    }
    status = bs.find(".//Status")
    if status is not None:
        sample["status"] = status.attrib.get("status")

    sra_ids = [t.text for t in bs.findall(".//Id") if t.attrib.get("db") == "SRA"]
    sample["SRA_IDs"] = ", ".join(sra_ids) if sra_ids else None

    bioprojects = [l.attrib.get("label") for l in bs.findall(".//Link")
                   if l.attrib.get("target") == "bioproject"]
    sample["BioProject"] = ", ".join(bioprojects) if bioprojects else None

    contact = bs.find(".//Owner/Contacts/Contact/Name")
    if contact is not None:
        sample["Submitter"] = " ".join([contact.findtext("First", ""),
                                        contact.findtext("Middle", ""),
                                        contact.findtext("Last", "")]).strip()
    owner = bs.find(".//Owner/Name")
    if owner is not None:
        sample["Owner"] = owner.text

    attrs = {}
    for a in bs.findall(".//Attribute"):
        key = a.attrib.get("attribute_name") or a.attrib.get("harmonized_name") or "unknown"
        attrs[key] = (attrs[key] + "; " + a.text) if key in attrs else a.text
    sample.update(attrs)
    return sample


def finish_without_new_runs(message):
    log(message)
    NEW_RUNS_FILE.write_text("")
    PENDING_FILE.write_text("0\n")
    sys.exit(0)


def limit_runs(df, max_runs):
    """Keep whole BioSamples until max_runs runs are reached (at least one BioSample).
    BioSamples are never split: step 3 skips any BioSample already in the metadata,
    so a run left behind from a BioSample that was saved would never be fetched again.
    Returns (rows kept, number of runs left for the next run)."""
    runs_per_bs = df.groupby("BioSampleID")["Run"].nunique().sort_index()
    if runs_per_bs.sum() <= max_runs:
        return df, 0
    keep, total = [], 0
    for bs, n in runs_per_bs.items():
        if keep and total + n > max_runs:
            break
        keep.append(bs)
        total += n
    return df[df["BioSampleID"].isin(keep)], int(runs_per_bs.sum() - total)


# --- Main ---
def main():
    log("=" * 60)
    log("TB-MX: NCBI search")
    log("=" * 60)

    # Step 1: Load existing metadata
    existing_runs = set()
    existing_bs   = set()
    df_existing   = pd.DataFrame()
    if METADATA_CSV.exists():
        df_existing   = pd.read_csv(METADATA_CSV, dtype=str).fillna("")
        existing_runs = set(df_existing["Run"].str.strip())
        existing_bs   = set(df_existing["BioSampleID"].str.strip())
        log(f"Existing CSV: {len(df_existing)} rows | {len(existing_runs)} runs | "
            f"{len(existing_bs)} BioSamples")
    else:
        log("No existing CSV (it will be created from scratch)")

    # Step 2: Search BioSample
    log("\nSearching BioSample...")
    handle = Entrez.esearch(db="biosample", term=BIOSAMPLE_QUERY, retmax=RETMAX)
    result = Entrez.read(handle); handle.close()
    all_bs_ids = result["IdList"]
    log(f"BioSamples in NCBI: {len(all_bs_ids)}")

    # Step 3: Download BioSample XML
    # esearch returns numeric UIDs (e.g. 56460836) while the CSV stores accessions
    # (e.g. SAMN56460836), so all records are downloaded and new BioSamples are
    # identified by accession.
    log(f"\nDownloading XML metadata for {len(all_bs_ids)} BioSamples...")
    n_batches = -(-len(all_bs_ids) // BATCH_SIZE)
    flat_samples = []
    for i in range(0, len(all_bs_ids), BATCH_SIZE):
        batch = all_bs_ids[i:i + BATCH_SIZE]
        log(f"  Batch {i // BATCH_SIZE + 1}/{n_batches}: {len(batch)} records...")
        time.sleep(0.4)       # stay under NCBI's request rate limit
        handle = Entrez.efetch(db="biosample", id=",".join(batch), retmode="xml")
        root = ET.fromstring(handle.read()); handle.close()
        for bs in root.findall(".//BioSample"):
            if bs.attrib.get("accession") in existing_bs:
                continue      # already in metadata_cleaned.csv
            flat_samples.append(parse_biosample(bs))

    df_bs_new = pd.DataFrame(flat_samples)
    log(f"  New BioSamples: {len(df_bs_new)}")
    if df_bs_new.empty:
        finish_without_new_runs("\nNo new BioSamples. Database is up to date.")

    # Step 4: Search SRA and download run info
    log("\nSearching SRA runs for the new BioSamples...")
    accessions  = df_bs_new["BioSampleID"].dropna().tolist()
    search_term = " OR ".join([f'"{a}"[BioSample]' for a in accessions])
    handle = Entrez.esearch(db="sra", term=search_term, retmax=RETMAX)
    result = Entrez.read(handle); handle.close()
    sra_ids = result["IdList"]
    log(f"  SRA records found: {len(sra_ids)}")
    if not sra_ids:
        finish_without_new_runs("No SRA runs for the new BioSamples.")

    handle = Entrez.efetch(db="sra", id=",".join(sra_ids), rettype="runinfo", retmode="text")
    df_sra_new = pd.read_csv(StringIO(handle.read().decode("utf-8"))); handle.close()
    log(f"  SRA runs downloaded: {len(df_sra_new)}")

    # Step 5: Merge BioSample + SRA and filter
    log("\nMerging BioSample + SRA...")
    merged = pd.merge(df_bs_new, df_sra_new,
                      left_on="BioSampleID", right_on="BioSample", how="left")
    merged = drop_similar_columns(merged, threshold=0.8)

    # Keep whole-genome sequencing runs that contain data
    if "LibraryStrategy" in merged.columns:
        merged = merged[merged["LibraryStrategy"] == "WGS"]
    if "spots" in merged.columns:
        merged = merged[pd.to_numeric(merged["spots"], errors="coerce").fillna(0) > 0]

    # Exclude laboratory reference strains (H37Rv / H37Ra) and in-vitro experiments:
    # they are not clinical isolates and must not enter surveillance statistics
    lab_mask = pd.Series(False, index=merged.index)
    if "ScientificName" in merged.columns:
        lab_mask |= merged["ScientificName"].fillna("").str.contains(r"H37R[va]", case=False)
    if "isolation_source" in merged.columns:
        lab_mask |= merged["isolation_source"].fillna("").str.contains(
            r"in vitro|laboratory", case=False)
    if lab_mask.any():
        log(f"  Excluded {int(lab_mask.sum())} runs from laboratory strains / in-vitro cultures")
        merged = merged[~lab_mask]

    # Drop runs that are already in the metadata
    if "Run" in merged.columns:
        merged = merged[~merged["Run"].isin(existing_runs)]
    log(f"  New runs after filters: {len(merged)}")
    if merged.empty:
        finish_without_new_runs("\nAll runs were already processed. Nothing to update.")

    # Keep at most MAX_RUNS runs in this pipeline run
    found = merged["Run"].nunique()
    merged, pending = limit_runs(merged, MAX_RUNS)
    if pending:
        log(f"  Limit of {MAX_RUNS} runs per pipeline run: processing {found - pending}, "
            f"{pending} left for the next run")
    PENDING_FILE.write_text(f"{pending}\n")

    # Step 6: Assign state and coordinates
    log("\nAssigning state and coordinates...")
    geo_col = next((c for c in merged.columns if "geo_loc" in c.lower()), None)
    if geo_col:
        geo = merged[geo_col].apply(extract_state)
        merged["state"] = geo.apply(lambda x: x[0])
        merged["lat"]   = geo.apply(lambda x: x[1])
        merged["lon"]   = geo.apply(lambda x: x[2])
    else:
        merged["state"] = ""
        merged["lat"]   = None
        merged["lon"]   = None
    log(f"  State identified: {merged['state'].ne('').sum()}/{len(merged)}")

    # Step 7: Append new rows to metadata_cleaned.csv
    log("\nUpdating metadata_cleaned.csv...")
    if not df_existing.empty:
        all_cols    = list(dict.fromkeys(list(df_existing.columns) + list(merged.columns)))
        df_existing = df_existing.reindex(columns=all_cols, fill_value="")
        merged      = merged.reindex(columns=all_cols, fill_value="")
        df_updated  = pd.concat([df_existing, merged], ignore_index=True)
    else:
        df_updated = merged.copy()
    df_updated.to_csv(METADATA_CSV, index=False)
    log(f"  Total rows in CSV: {len(df_updated)} (+{len(merged)} new)")

    # Step 8: Write new_runs.txt
    new_run_ids = sorted(r.strip() for r in merged["Run"].dropna().tolist()
                         if str(r).strip().startswith(("SRR", "ERR", "DRR")))
    NEW_RUNS_FILE.write_text("\n".join(new_run_ids) + "\n")

    log("\n" + "=" * 60)
    log(f"RESULT: {len(new_run_ids)} new runs to process"
        + (f" ({pending} left for the next run)" if pending else ""))
    for run_id in new_run_ids:
        log(f"  {run_id}")
    log("\nFiles updated:")
    log(f"  {METADATA_CSV}")
    log(f"  {NEW_RUNS_FILE}")
    log(f"  {PENDING_FILE}")
    log("=" * 60)


if __name__ == "__main__":
    main()
