#!/usr/bin/env python3
#Fetch available biosamples in NCBI
  #1. Load original run
  #2. esearch on BioSample
  #3. efetch XML of new BioSamples
  #4. esearch + efetch runinfo SRA
  #5. Merge BioSample + SRA
  #6. Looks up states, cleans it 
  #7. Add new row for new biosamples on metadata_cleaned.csv
  #8. Saves ~/new_runs.txt with the new  Run IDs to process

import os, sys, time, difflib, unicodedata
from io import StringIO
from pathlib import Path
import pandas as pd
import xml.etree.ElementTree as ET
from Bio import Entrez

# Configuration
Entrez.email = "daniela.santana@uabc.edu.mx"
METADATA_CSV  = Path.home() / "metadata_cleaned.csv"
NEW_RUNS_FILE = Path.home() / "new_runs.txt"
RETMAX        = 2000

# Map coordinates for cleaning location (state) data
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

def log(msg): print(msg, flush=True)

def normalize(text):
    """'Nuevo León ' -> 'nuevo leon'"""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())

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
    cols, drop = df.columns.tolist(), set()
    for i in range(len(cols)):
        for j in range(i+1, len(cols)):
            c1, c2 = cols[i], cols[j]
            if c1 in drop or c2 in drop: continue
            if difflib.SequenceMatcher(None, c1.lower(), c2.lower()).ratio() < threshold:
                continue
            s1, s2 = df[c1], df[c2]
            if not (pd.api.types.is_numeric_dtype(s1) and pd.api.types.is_numeric_dtype(s2)):
                match_frac = ((s1==s2)|(s1.isna()&s2.isna())).sum()/len(df)
                if match_frac > 0.95:
                    drop.add(c1 if s1.isna().sum() >= s2.isna().sum() else c2)
    return df.drop(columns=list(drop))

# STEP 1: Load original run results
log("="*60)
log("TB-MX: Busqueda en NCBI")
log("="*60)

existing_runs = set()
existing_bs   = set()
df_existing   = pd.DataFrame()

if METADATA_CSV.exists():
    df_existing   = pd.read_csv(METADATA_CSV, dtype=str).fillna("")
    existing_runs = set(df_existing["Run"].str.strip())
    existing_bs   = set(df_existing["BioSampleID"].str.strip())
    log(f"CSV existente: {len(df_existing)} filas | {len(existing_runs)} runs | {len(existing_bs)} BioSamples")
else:
    log("Sin CSV existente (se creara desde cero)")

# STEP 2: esearch BioSample
log("\nBuscando en BioSample...")
QUERY = (
    '"Mycobacterium tuberculosis"[Organism] '
    'AND ("Mexico"[Organism] OR "Mexico"[All Fields]) '
    'NOT ("Mycobacterium tuberculosis variant bovis"[Organism] OR "mice"[All fields])'
)
h = Entrez.esearch(db="biosample", term=QUERY, retmax=RETMAX)
res = Entrez.read(h); h.close()
all_bs_ids = res["IdList"]
log(f"BioSamples en NCBI: {len(all_bs_ids)}")

# esearch returns numeric UIDs (e.g. 56460836), but the CSV stores accessions
# (e.g. SAMN56460836). They can't be compared directly, so all records are
# fetched and new BioSamples are identified by accession inside the loop below.

# STEP 3: efetch XML of new BioSamples
log(f"\nDescargando metadata XML de {len(all_bs_ids)} BioSamples...")
BATCH = 200
flat_samples = []

for i in range(0, len(all_bs_ids), BATCH):
    batch = all_bs_ids[i:i+BATCH]
    log(f"  Lote {i//BATCH+1}/{-(-len(all_bs_ids)//BATCH)}: {len(batch)} registros...")
    time.sleep(0.4)

    h    = Entrez.efetch(db="biosample", id=",".join(batch), retmode="xml")
    root = ET.fromstring(h.read()); h.close()

    for bs in root.findall(".//BioSample"):
      if bs.attrib.get("accession") in existing_bs:
        continue #already in metadata_cleaned.csv
      s = {
          "BioSampleID":      bs.attrib.get("accession"),
          "publication_date": bs.attrib.get("publication_date"),
          "submission_date":  bs.attrib.get("submission_date"),
      }
      st = bs.find(".//Status")
      if st is not None: s["status"] = st.attrib.get("status")

      sra_ids = [t.text for t in bs.findall(".//Id") if t.attrib.get("db")=="SRA"]
      s["SRA_IDs"] = ", ".join(sra_ids) if sra_ids else None

      bps = [l.attrib.get("label") for l in bs.findall(".//Link")
             if l.attrib.get("target")=="bioproject"]
      s["BioProject"] = ", ".join(bps) if bps else None

      cn = bs.find(".//Owner/Contacts/Contact/Name")
      if cn is not None:
          s["Submitter"] = " ".join([cn.findtext("First",""),
                                      cn.findtext("Middle",""),
                                      cn.findtext("Last","")]).strip()
      ow = bs.find(".//Owner/Name")
      if ow is not None: s["Owner"] = ow.text

      attrs = {}
      for a in bs.findall(".//Attribute"):
          k = a.attrib.get("attribute_name") or a.attrib.get("harmonized_name") or "unknown"
          v = a.text
          attrs[k] = (attrs[k]+"; "+v) if k in attrs else v
      
      s.update(attrs)
      flat_samples.append(s)

df_bs_new = pd.DataFrame(flat_samples)
log(f"  BioSamples nuevos: {len(df_bs_new)}")

if df_bs_new.empty:
    log("\nSin BioSamples nuevos. Base de datos actualizada.")
    NEW_RUNS_FILE.write_text("")
    sys.exit(0)
  
#STEP 4: esearch + efetch SRA runinfo
log(f"\nBuscando runs SRA para los nuevos BioSamples...")
accessions  = df_bs_new["BioSampleID"].dropna().tolist()
search_term = " OR ".join([f'"{a}"[BioSample]' for a in accessions])

h   = Entrez.esearch(db="sra", term=search_term, retmax=RETMAX)
res = Entrez.read(h); h.close()
sra_ids = res["IdList"]
log(f"  Registros SRA encontrados: {len(sra_ids)}")

if not sra_ids:
    log("Sin runs SRA para los nuevos BioSamples.")
    NEW_RUNS_FILE.write_text("")
    sys.exit(0)

h = Entrez.efetch(db="sra", id=",".join(sra_ids), rettype="runinfo", retmode="text")
df_sra_new = pd.read_csv(StringIO(h.read().decode("utf-8"))); h.close()
log(f"  Runs SRA descargados: {len(df_sra_new)}")

# STEP 5: Merge data (BioSamples + SRA)
log("\n Uniendo BioSample + SRA...")
merged = pd.merge(df_bs_new, df_sra_new,
                  left_on="BioSampleID", right_on="BioSample", how="left")
merged = drop_similar_columns(merged, threshold=0.8)

# Filtrar WGS con datos
if "LibraryStrategy" in merged.columns:
    merged = merged[merged["LibraryStrategy"]=="WGS"]
if "spots" in merged.columns:
    merged = merged[pd.to_numeric(merged["spots"], errors="coerce").fillna(0) > 0]

# Eliminar runs ya existentes
if "Run" in merged.columns:
    merged = merged[~merged["Run"].isin(existing_runs)]

log(f"  Runs nuevos tras filtros: {len(merged)}")

if merged.empty:
    log("\nTodos los runs ya estaban procesados. Sin actualizaciones.")
    NEW_RUNS_FILE.write_text("")
    sys.exit(0)

# STEP 6: Unify location data, look up states and clean it 
log("\nExtrayendo estado y coordenadas...")
geo_col = next((c for c in merged.columns if "geo_loc" in c.lower()), None)
if geo_col:
    geo = merged[geo_col].apply(extract_state)
    merged["state"] = geo.apply(lambda x: x[0])
    merged["lat"]   = geo.apply(lambda x: x[1])
    merged["lon"]   = geo.apply(lambda x: x[2])
else:
    merged["state"] = ""; merged["lat"] = None; merged["lon"] = None

log(f"  Con estado identificado: {merged['state'].ne('').sum()}/{len(merged)}")

# STEP 7: Update metadata_cleaned.csv with new info
log("\nActualizando metadata_cleaned.csv...")
if not df_existing.empty:
    all_cols = list(dict.fromkeys(list(df_existing.columns) + list(merged.columns)))
    df_existing = df_existing.reindex(columns=all_cols, fill_value="")
    merged      = merged.reindex(columns=all_cols, fill_value="")
    df_updated  = pd.concat([df_existing, merged], ignore_index=True)
else:
    df_updated = merged.copy()

df_updated.to_csv(METADATA_CSV, index=False)
log(f"  Total filas en CSV: {len(df_updated)} (+{len(merged)} nuevas)")

# STEP 8: Save new_runs.txt
new_run_ids = [r.strip() for r in merged["Run"].dropna().tolist()
               if str(r).strip().startswith(("SRR","ERR","DRR"))]
NEW_RUNS_FILE.write_text("\n".join(sorted(new_run_ids)) + "\n")

log("\n" + "="*60)
log(f"RESULTADO: {len(new_run_ids)} runs nuevos a procesar")
for r in sorted(new_run_ids):
    log(f"  {r}")
log(f"\nArchivos actualizados:")
log(f"  {METADATA_CSV}")
log(f"  {NEW_RUNS_FILE}")
log("="*60)
