#!/usr/bin/env python3

#Busqueda de muestras en NCBI
  #1. esearch en BioSample
  #2. efetch XML de BioSamples nuevos
  #3. esearch + efetch runinfo SRA
  #4. Merge BioSample + SRA
  #5. Geocodifica estados
  #6. Agrega filas nuevas a metadata_cleaned.csv
  #7. Guarda ~/new_runs.txt con los Run IDs a procesar

#Uso: python pipeline/01_buscador.py

import os, sys, time, difflib
from io import StringIO
from pathlib import Path
import pandas as pd
import xml.etree.ElementTree as ET
from Bio import Entrez

# Configuracion
Entrez.email = "daniela.santana@uabc.edu.mx"
METADATA_CSV  = Path.home() / "metadata_cleaned.csv"
NEW_RUNS_FILE = Path.home() / "new_runs.txt"
RETMAX        = 2000

# Mapa coordenadas por estado
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
    "Mexico":             (19.3588,  -99.8237),
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

def extract_state(geo_loc_name):
    if not geo_loc_name or pd.isna(geo_loc_name):
        return "", None, None
    geo = str(geo_loc_name).replace("Mexico:", "").strip()
    state_raw = geo.split(",")[0].strip()
    for key, coords in STATE_COORDS.items():
        if key.lower() in state_raw.lower() or state_raw.lower() in key.lower():
            return key, coords[0], coords[1]
    return state_raw, None, None

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

# PASO 1: Cargar metadata existente
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

# PASO 2: esearch BioSample
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

# Solo los nuevos
new_bs_ids = [b for b in all_bs_ids if b not in existing_bs]
log(f"BioSamples nuevos (no en CSV): {len(new_bs_ids)}")

if not new_bs_ids:
    log("\nSin BioSamples nuevos. Base de datos actualizada.")
    NEW_RUNS_FILE.write_text("")
    sys.exit(0)

# PASO 3: efetch XML de BioSamples nuevos
log(f"\nDescargando metadata XML de {len(new_bs_ids)} BioSamples nuevos...")
BATCH = 200
flat_samples = []

for i in range(0, len(new_bs_ids), BATCH):
    batch = new_bs_ids[i:i+BATCH]
    log(f"  Lote {i//BATCH+1}/{-(-len(new_bs_ids)//BATCH)}: {len(batch)} registros...")
    time.sleep(0.4)

    h    = Entrez.efetch(db="biosample", id=",".join(batch), retmode="xml")
    root = ET.fromstring(h.read()); h.close()

    for bs in root.findall(".//BioSample"):
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
log(f"  BioSamples parseados: {len(df_bs_new)}")

# PASO 4: esearch + efetch SRA runinfo
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

h          = Entrez.efetch(db="sra", id=",".join(sra_ids), rettype="runinfo", retmode="text")
df_sra_new = pd.read_csv(StringIO(h.read().decode("utf-8"))); h.close()
log(f"  Runs SRA descargados: {len(df_sra_new)}")

# PASO 5: Merge datos
log("\nMerging BioSample + SRA...")
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

# PASO 6: Geocodificar
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

# PASO 7: Actualizar metadata_cleaned.csv
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

# PASO 8: Guardar new_runs.txt
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
