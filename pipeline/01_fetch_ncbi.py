#!/usr/bin/env python3
#Paso 1 del pipeline
  #1. Carga la metadata existente (metadata_cleaned.csv)
  #2. Busca BioSamples de M. tuberculosis de Mexico
  #3. Descarga el XML de los BioSamples nuevos
  #4. Busca SRA y los descarga
  #5. Une BioSample + SRA, conserva WGS con datos 
  #6. Asigna estado y coordenadas con geo_loc_name
  #7. Agrega filas nuevas a metadata_cleaned.csv para guardas las muestras nuevas
  #8. Escribe em new_runs.txt los runs a procesar 

import sys #para terminar ejecucion si no hay muestras nuevas
import time #para pausas en consultas a NCBI
import difflib #similitud de textos, identificar columnas duplicadas
import unicodedata #normalizar texto, para procesar estados
import xml.etree.ElementTree as ET #lee archivo XML
from io import StringIO #leer CSV en memoria con pandas
from pathlib import Path #rutas de archivos
import pandas as pd #DataFrames
from Bio import Entrez #para API de busqueda en NCBI

# Configuración y rutas de archivos
Entrez.email = "daniela.santana@uabc.edu.mx"
METADATA_CSV = Path.home()/"metadata_cleaned.csv"
NEW_RUNS_FILE = Path.home()/"new_runs.txt"
PENDING_FILE = Path.home()/"pending_runs.txt"   #corridas pendientes, se alcanza el max de 25 runs
NO_RUN_FILE = Path.home()/"new_no_run_biosamples.txt"  # BioSamples sin corridas
RETMAX = 2000   #máximo de IDS por consulta esearch a NCBI
BATCH_SIZE = 200  # Lote max por solicitud
SRA_BATCH = 100  # lote max en consulta de SRA
MAX_RUNS = 25 #Max de SRA a procesar para no pasar limite de github de 6 horas

#Filtro de busqueda en NCBI
BIOSAMPLE_QUERY = (
    '"Mycobacterium tuberculosis"[Organism] ''AND ("Mexico"[Organism] OR "Mexico"[All Fields]) '
    'NOT ("Mycobacterium tuberculosis variant bovis"[Organism] OR "mice"[All fields])'
)

# Coordenadas representativas a cada estado (para ubicación en el mapa)
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

#Limpieza de escritura de estados, formas encontradas en NCBI 
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

#Columnas relevantes, que nunca deben eliminarse como duplicadas
KEY_COLUMNS = {"BioSampleID", "Run", "geo_loc_name", "collection_date",
               "isolation_source", "host", "spots", "BioProject_x", "BioProject_y"}

#Funciones auxiliares
def log(msg): #Imprime mensajes de inmediato en github, para conocer estado de ejecución
    print(msg, flush=True)

def normalize(text): #separada letras acentuadas en letra + acento y después elimina el acento
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split()) #minusuculas y sin espacios repetidos
      # "Nuevo León" lo convierte en "nuevo leon"

#Tabla de busqueda de estados, del nombre normalizado busca el nombre oficial, une los dos diccionarios
STATE_LOOKUP = {normalize(s): s for s in STATE_COORDS} | STATE_ALIASES

def extract_state(geo_loc_name): #Coordenada a cada estado
    if pd.isna(geo_loc_name) or ":" not in str(geo_loc_name):
        return "", None, None
    for part in str(geo_loc_name).split(":", 1)[1].split(","): #Si no tiene : solo es el país
        state = STATE_LOOKUP.get(normalize(part))
        if state:
            return state, *STATE_COORDS[state] #agrega lat, lon
    return "", None, None 
   # 'Mexico: Xalapa, Veracruz' lo convierte en ('Veracruz', lat, lon)
   # Si no se menciona estado o no es reconocido ('', None, None)

#Elimina columnas casi duplicadas generadas al unir BioSample + SRA 
#Las columnas clave siempre se conservan
def drop_similar_columns(df, threshold=0.8): 
    cols, drop = df.columns.tolist(), set()
    for i in range(len(cols)):  #itera para comparar columnas
        for j in range(i + 1, len(cols)):
            c1, c2 = cols[i], cols[j]
            if c1 in drop or c2 in drop:
                continue
            if c1 in KEY_COLUMNS and c2 in KEY_COLUMNS: #nunca elimina si columna es relevante
                continue
            if difflib.SequenceMatcher(None, c1.lower(), c2.lower()).ratio() < threshold:
                continue
            s1, s2 = df[c1], df[c2]
            if not (pd.api.types.is_numeric_dtype(s1) and pd.api.types.is_numeric_dtype(s2)): #solo compara columnas de texto
                match_frac = ((s1 == s2) | (s1.isna() & s2.isna())).sum() / len(df) #fracción de similitud
                if match_frac > 0.95: #si hay similitud mayor al 95%
                    if c1 in KEY_COLUMNS: #conserva la columna clave, si no hay, elimina aquella con mas vacíos
                        drop.add(c2)
                    elif c2 in KEY_COLUMNS:
                        drop.add(c1)
                    else:
                        drop.add(c1 if s1.isna().sum() >= s2.isna().sum() else c2)
    return df.drop(columns=list(drop))

#Convierte elementos <XML? en un diccionario plano
def parse_biosample(bs):
    sample = {  #Identificadores relevantes a tomar del XML del BioSample
        "BioSampleID":      bs.attrib.get("accession"),
        "publication_date": bs.attrib.get("publication_date"),
        "submission_date":  bs.attrib.get("submission_date"),
    }
    status = bs.find(".//Status") #estado del registro en NCBI
    if status is not None:
        sample["status"] = status.attrib.get("status")

    sra_ids = [t.text for t in bs.findall(".//Id") if t.attrib.get("db") == "SRA"] # SRA vinculado
    sample["SRA_IDs"] = ", ".join(sra_ids) if sra_ids else None  #unido a un solo texto

    bioprojects = [l.attrib.get("label") for l in bs.findall(".//Link") #BioProject vinculado
                   if l.attrib.get("target") == "bioproject"]
    sample["BioProject"] = ", ".join(bioprojects) if bioprojects else None

    contact = bs.find(".//Owner/Contacts/Contact/Name") #Contacto de quien subio la muestra
    if contact is not None:
        sample["Submitter"] = " ".join([contact.findtext("First", ""),
                                        contact.findtext("Middle", ""),
                                        contact.findtext("Last", "")]).strip()
    owner = bs.find(".//Owner/Name") #Institución dueña del registro
    if owner is not None:
        sample["Owner"] = owner.text

    attrs = {} #Convierte cada <Attribute> de XML en una columna
    for a in bs.findall(".//Attribute"):
        key = a.attrib.get("attribute_name") or a.attrib.get("harmonized_name") or "unknown"
        attrs[key] = (attrs[key] + "; " + a.text) if key in attrs else a.text
    sample.update(attrs)
    return sample

def finish_without_new_runs(message): #Escribe los archivos de salida vacíos y termina el srcipt
    log(message)
    NEW_RUNS_FILE.write_text("")
    PENDING_FILE.write_text("0\n")
    NO_RUN_FILE.write_text("0\n")
    sys.exit(0)

#Conserva BioSamples completos hasta alcanzar MAX_RUNS, nunca se parte un BioSample
def limit_runs(df, max_runs): 
    runs_per_bs = df.groupby("BioSampleID")["Run"].nunique().sort_index() #Numero de runs distintos por BioSample
    if runs_per_bs.sum() <= max_runs: #Si no se llega el limite, se guarda todo
        return df, 0
    keep, total = [], 0
    for bs, n in runs_per_bs.items():
        if keep and total + n > max_runs: #se detiene antes de pasar el limite
            break
        keep.append(bs)
        total += n
    return df[df["BioSampleID"].isin(keep)], int(runs_per_bs.sum() - total)

#PRINCIPAL
def main():
    log("=" * 60)
    log("TB-MX: NCBI search")
    log("=" * 60)

    #Paso 1: cargar metadata existente
    # "Existentes" son aquellos BioSamples que tienen run, aquellos sin runs se vuelven a analizar por si son publicados en NCBI
    existing_runs = set()
    existing_bs = set()
    no_run_bs_csv = set()
    df_existing = pd.DataFrame()
    if METADATA_CSV.exists():
        df_existing = pd.read_csv(METADATA_CSV, dtype=str).fillna("") #lee todo, convierte celdas vacias en ""
        has_run = df_existing["Run"].str.strip() != "" #etiqueta TRUE en la filas con run ID
        existing_runs = set(df_existing.loc[has_run, "Run"].str.strip())
        existing_bs = set(df_existing.loc[has_run, "BioSampleID"].str.strip())
        no_run_bs_csv = set(df_existing["BioSampleID"].str.strip()) - existing_bs #BioSamples sin run
        log(f"El CSV de metadata contiene: {len(df_existing)} filas | {len(existing_runs)} corridas | "
            f"{len(existing_bs)} BioSamples con corridas | {len(no_run_bs_csv)} sin corridas") #imprime conteo
    else:
        log("No existe el CSV de metadata (se creará desde cero)")

    # Paso 2: buscar BioSamples en NCBI
    log("\Buscando BioSamples en NCBI...")
    handle = Entrez.esearch(db="biosample", term=BIOSAMPLE_QUERY, retmax=RETMAX)
    result = Entrez.read(handle); handle.close()
    all_bs_ids = result["IdList"]
    log(f"BioSamples en NCBI: {len(all_bs_ids)}")

    #  Paso 3: descargar el XML de los BioSamples
    # La busqueda esearch despliega UIDs, pero queremos IDs de acceso
    log(f"\nDescargando archivos XML de {len(all_bs_ids)} BioSamples...")
    n_batches = -(-len(all_bs_ids) // BATCH_SIZE)
    flat_samples = []
    for i in range(0, len(all_bs_ids), BATCH_SIZE):
        batch = all_bs_ids[i:i + BATCH_SIZE]
        log(f"  Lote {i // BATCH_SIZE + 1}/{n_batches}: {len(batch)} registros...")
        time.sleep(0.4) # respeta limite de solicitudes de NCBI
        handle = Entrez.efetch(db="biosample", id=",".join(batch), retmode="xml")
        root = ET.fromstring(handle.read()); handle.close()
        for bs in root.findall(".//BioSample"):
            if bs.attrib.get("accession") in existing_bs: #obtiene el ID de acceso del BioSample
                continue      # ya esta en metadata_cleaned con sus corridas
            flat_samples.append(parse_biosample(bs))

    df_bs_new = pd.DataFrame(flat_samples) #Una fila por BioSample a revisar

  #Se puede mencionar Mexico en algun otro atributo del BioSample, se implemento este filtro para conservar
  #muestras que especifican Mexico en el atributo geo_loc_name, registros sin este atributo se conservan
    if not df_bs_new.empty and "geo_loc_name" in df_bs_new.columns:
        country = (df_bs_new["geo_loc_name"].fillna("").astype(str)
                   .str.split(":").str[0].map(normalize))
        other_country = (country != "") & (country != "mexico")
        if other_country.any():
            log(f"  Se excluyeron {int(other_country.sum())} BioSamples de otros países: "
                + ", ".join(sorted(set(df_bs_new.loc[other_country, "geo_loc_name"]))))
            df_bs_new = df_bs_new[~other_country]
    log(f"  BioSamples a revisat: {len(df_bs_new)} "
        f"({df_bs_new['BioSampleID'].isin(no_run_bs_csv).sum() if not df_bs_new.empty else 0} "
        f"guardados sin corridas)")
    if df_bs_new.empty:
        finish_without_new_runs("\nNo hay BioSamples nuevos. Base de datos al día.")

    # Paso 4: busca SRA y descarga la información de los runs, por lotes
    log("\nBuscando corridas de SRA de los BioSamples...")
    accessions = df_bs_new["BioSampleID"].dropna().tolist()
    sra_ids = []
    n_batches = -(-len(accessions) // SRA_BATCH)
    for i in range(0, len(accessions), SRA_BATCH):
        batch = accessions[i:i + SRA_BATCH]
        log(f"  Lote de búsqueda {i // SRA_BATCH + 1}/{n_batches}: {len(batch)} BioSamples...")
        time.sleep(0.4)     
        search_term = " OR ".join([f'"{a}"[BioSample]' for a in batch])
        handle = Entrez.esearch(db="sra", term=search_term, retmax=RETMAX)
        result = Entrez.read(handle); handle.close()
        sra_ids.extend(result["IdList"])
    sra_ids = list(dict.fromkeys(sra_ids))   #quita duplicados
    log(f"  Registros de SRA encontrados: {len(sra_ids)}")

    run_tables = [] #Descarga la tabla "runinfo" de la metadata de SRA
    for i in range(0, len(sra_ids), BATCH_SIZE):
        batch = sra_ids[i:i + BATCH_SIZE]
        time.sleep(0.4)
        handle = Entrez.efetch(db="sra", id=",".join(batch), rettype="runinfo", retmode="text")
        text = handle.read().decode("utf-8"); handle.close()
        if text.strip():
            run_tables.append(pd.read_csv(StringIO(text)))
    df_sra_new = (pd.concat(run_tables, ignore_index=True) if run_tables #une todos los lotes, si no hay tabla vacía
                  else pd.DataFrame(columns=["BioSample", "Run"]))
    log(f"  Runs de SRA descargados: {len(df_sra_new)}")

    # Paso 5: Unir Datos de BioSample y SRA, y filtrar
    log("\nUniendo datos de BioSample y SRA...")
    merged = pd.merge(df_bs_new, df_sra_new,
                      left_on="BioSampleID", right_on="BioSample", how="left")
    merged = drop_similar_columns(merged, threshold=0.8)
    
    # Filtro para exluir muestras que no pertencen, se excluye el BioSample completo, con o sin run
    lab_mask = pd.Series(False, index=merged.index)
    if "ScientificName" in merged.columns: #Excluye cepas de referencia de laboratorio (H37Rv / H37Ra) 
        lab_mask |= merged["ScientificName"].fillna("").str.contains(r"H37R[va]", case=False)
    if "isolation_source" in merged.columns: #Excluye experimentos in vitro
        lab_mask |= merged["isolation_source"].fillna("").str.contains(
            r"in vitro|laboratory", case=False)
    lab_bs = set(merged.loc[lab_mask, "BioSampleID"])
    if lab_bs: 
        log(f"  Excluidos {len(lab_bs)} BioSamples de cepas de laboratorio o cultivos in vitro")
    merged = merged[~merged["BioSampleID"].isin(lab_bs)]

    # Conserva runs de secuenciación de genoma completos con datos
    usable = merged
    if "LibraryStrategy" in usable.columns: #solo secuenciación de genoma completo
        usable = usable[usable["LibraryStrategy"] == "WGS"]
    if "spots" in usable.columns: #secuencias con mas de 0 lecturas
        usable = usable[pd.to_numeric(usable["spots"], errors="coerce").fillna(0) > 0]
    if "Run" in usable.columns: #debe tener ID de run y no estar ya en la metadata
        usable = usable[usable["Run"].fillna("").str.strip() != ""]
        usable = usable[~usable["Run"].isin(existing_runs)]

    # BioSamples sin run utilizables (sin run, run vacio, o no WGS) se guardan sin datos en RUN 
    checked_bs     = set(df_bs_new["BioSampleID"]) - lab_bs
    no_run_bs      = checked_bs - set(usable["BioSampleID"])
    new_no_run_bs  = sorted(no_run_bs - no_run_bs_csv)
    df_no_run      = (df_bs_new[df_bs_new["BioSampleID"].isin(new_no_run_bs)] #Sn columna RUN
                      .drop_duplicates(subset="BioSampleID").copy())
    log(f"  Runs nuevos tras filtros: {usable['Run'].nunique() if 'Run' in usable else 0}")
    log(f"  BioSamples sin run: {len(no_run_bs)} ({len(new_no_run_bs)} nuevos)")

    # Conserva sólo 25 (MAX_RUNS) en esta corrida
    pending = 0
    if not usable.empty:
        found = usable["Run"].nunique()
        usable, pending = limit_runs(usable, MAX_RUNS)
        if pending:
            log(f"  Límite {MAX_RUNS} runs por ejecución: {found - pending} a procesar, "
                f"{pending} pendientes para la próxima ejecución")

    if usable.empty and df_no_run.empty:
        finish_without_new_runs("\nSin muestras a procesar: No hay BioSamples ni runs nuevos.")
    PENDING_FILE.write_text(f"{pending}\n")
    NO_RUN_FILE.write_text(f"{len(df_no_run)}\n")

    # Paso 6: asignar estado y coordenadas
    log("\nAsignando estado y coordenadas...")
    new_rows = pd.concat([usable, df_no_run], ignore_index=True) #añade filas nuevas por BioSample nuevo
    geo_col = next((c for c in new_rows.columns if "geo_loc" in c.lower()), None) #busca la columna geo_loc_name
    if geo_col:
        geo = new_rows[geo_col].apply(extract_state)  #toma el valor (estado, lat, lon) y lo separa en 3 columnas
        new_rows["state"] = geo.apply(lambda x: x[0])
        new_rows["lat"] = geo.apply(lambda x: x[1])
        new_rows["lon"] = geo.apply(lambda x: x[2])
    else:
        new_rows["state"] = ""
        new_rows["lat"]   = None
        new_rows["lon"]   = None
    log(f"  Estado identificado: {new_rows['state'].ne('').sum()}/{len(new_rows)}")

    # Paso 7: agregar filas nuevas al archivo metadata_cleaned.csv con los nuevos BioSamples identificados    
    log("\nActualizadno metadata_cleaned.csv...")
    if not df_existing.empty:
        now_with_runs = set(usable["BioSampleID"]) & no_run_bs_csv
        if now_with_runs:
            log(f"  {len(now_with_runs)} BioSamples guardados que ahora tienen runs")
            df_existing = df_existing[~(df_existing["BioSampleID"].isin(now_with_runs)
                                        & (df_existing["Run"].str.strip() == ""))]
        all_cols = list(dict.fromkeys(list(df_existing.columns) + list(new_rows.columns)))
        df_existing = df_existing.reindex(columns=all_cols, fill_value="")
        new_rows = new_rows.reindex(columns=all_cols, fill_value="")
        df_updated = pd.concat([df_existing, new_rows], ignore_index=True)
    else:
        df_updated = new_rows.copy()
    df_updated.to_csv(METADATA_CSV, index=False)
    log(f"  Total de BioSamples (filas) en el CSV: {len(df_updated)} (+{len(usable)} con runs, "
        f"+{len(df_no_run)} sin run)")

    # Paso 8: escribir new_runs.txt
    new_run_ids = sorted(r.strip() for r in usable["Run"].dropna().tolist()
                         if str(r).strip().startswith(("SRR", "ERR", "DRR"))) #filtra runs válidos
    NEW_RUNS_FILE.write_text("\n".join(new_run_ids) + "\n" if new_run_ids else "") #escribe una fila por run

#Resumen de 01_fetch_ncbi
    log("\n" + "=" * 60)
    log(f"RESULTDO: {len(new_run_ids)} runs nuevos a procesar"
        + (f" ({pending} pendientes para la siguiente ejecución del pipeline)" if pending else ""))
    for run_id in new_run_ids:
        log(f"  {run_id}")
    log(f"New BioSamples nuevos sin run: {len(df_no_run)}")
    log("\nArchivos actualizados:")
    log(f"  {METADATA_CSV}")
    log(f"  {NEW_RUNS_FILE}")
    log(f"  {PENDING_FILE}")
    log(f"  {NO_RUN_FILE}")
    log("=" * 60)

if __name__ == "__main__":  #Ejecuta main
    main()
