#!/usr/bin/env python3

#Correr TB-Profiler
  #1. Lee ~/new_runs.txt
  #2. Corre TB-Profiler en runs nuevos
  #3. JSONs nuevos se guardan en ~/json_cache/

#Uso: python pipeline/01_corrertbprofiler.py

import subprocess, time, os, json, shutil
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# CONFIGURACIÓN
WORKDIR = Path.home() / "workdir"
JSON_CACHE = Path.home() / "json_cache"
NEW_RUNS_FILE = Path.home() / "new_runs.txt"
LOG_FILE = Path.home() / "run_tbprofiler_update.log"

N_WORKERS = 2
TIMEOUT_DL = 3600
TIMEOUT_FQ = 1800
TIMEOUT_PROF = 10800
MIN_DISK_GB = 5

WORKDIR.mkdir(exist_ok=True)
JSON_CACHE.mkdir(exist_ok=True)

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
        f.flush()
    print(line, flush=True)

def disk_free_gb():
    st = os.statvfs(WORKDIR)
    return (st.f_bavail * st.f_frsize) / 1e9


def find_json(wdir, run_id):
    candidates = [
        os.path.join(wdir, "results", "results", f"{run_id}.results.json"),
        os.path.join(wdir, "results", f"{run_id}.results.json"),
        os.path.join(wdir, f"{run_id}.results.json"),
        os.path.join(Path.home(), "results", f"{run_id}.results.json"),
    ]
    return next((p for p in candidates if os.path.exists(p)), None)


def process_sample(run_id):
    start = time.time()
    wdir = str(WORKDIR / run_id)
    r1 = os.path.join(wdir, f"{run_id}_1.fastq.gz")
    r2 = os.path.join(wdir, f"{run_id}_2.fastq.gz")
    sra_dir = f"/tmp/{run_id}"
    sra_file = os.path.join(sra_dir, f"{run_id}.sra")

    def elapsed():
        return (time.time() - start) / 60

    def cleanup():
        shutil.rmtree(wdir, ignore_errors=True)
        shutil.rmtree(sra_dir, ignore_errors=True)

    try:
        if disk_free_gb() < MIN_DISK_GB:
            return run_id, False, f"Disco lleno ({disk_free_gb():.1f} GB libres)", elapsed()

        shutil.rmtree(wdir, ignore_errors=True)
        os.makedirs(wdir, exist_ok=True)

        #Descarga prefetch
        shutil.rmtree(sra_dir, ignore_errors=True)
        r = subprocess.run(
            ["prefetch", "--max-size", "50G",
             "--output-directory", "/tmp", run_id],
            capture_output=True, text=True, timeout=TIMEOUT_DL)

        if r.returncode == 0 and os.path.exists(sra_file):
            subprocess.run(
                ["fasterq-dump", "--split-files", "--threads", "2",
                 "--outdir", wdir, "--temp", wdir, sra_file],
                capture_output=True, text=True, timeout=TIMEOUT_FQ)
            for fq in [f"{run_id}_1.fastq", f"{run_id}_2.fastq", f"{run_id}.fastq"]:
                fq_path = os.path.join(wdir, fq)
                if os.path.exists(fq_path):
                    subprocess.run(["gzip", "-f", fq_path], check=False)
            shutil.rmtree(sra_dir, ignore_errors=True)

        # Fallback fastq-dump
        if not os.path.exists(r1):
            r = subprocess.run(
                ["fastq-dump", "--split-files", "--gzip",
                 "--outdir", wdir, run_id],
                capture_output=True, text=True, timeout=TIMEOUT_DL)
            if r.returncode != 0:
                cleanup()
                return run_id, False, f"Download failed: {r.stderr[:200]}", elapsed()

        # Detectar single vs paired
        r1_se = os.path.join(wdir, f"{run_id}.fastq.gz")
        if os.path.exists(r1_se) and not os.path.exists(r1):
            os.rename(r1_se, r1)

        if not os.path.exists(r1):
            cleanup()
            return run_id, False, "FASTQ no encontrado tras descarga", elapsed()

        paired = os.path.exists(r2)
        results_dir = os.path.join(wdir, "results")
        os.makedirs(results_dir, exist_ok=True)

        #2. CORRER TB-Profiler
        cmd = ["tb-profiler", "profile",
               "-1", r1,
               "-p", run_id, "-t", "4",
               "--txt", "--csv",
               "--dir", results_dir]
        if paired:
            cmd += ["-2", r2]

        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=TIMEOUT_PROF, cwd=wdir)

        json_src = find_json(wdir, run_id)
        if json_src is None:
            err = r.stderr[-300:] if r.stderr else "JSON no encontrado"
            cleanup()
            return run_id, False, f"TB-Profiler: {err}", elapsed()

        # Validar JSON
        try:
            with open(json_src) as jf:
                d = json.load(jf)
            if "qc" not in d:
                cleanup()
                return run_id, False, "JSON sin campo qc", elapsed()
        except Exception as e:
            cleanup()
            return run_id, False, f"JSON inválido: {e}", elapsed()

        # 3. GUARDAR JSONs NUEVOS
        dst = JSON_CACHE / f"{run_id}.results.json"
        shutil.copy2(json_src, dst)

        cleanup()
        return run_id, True, "OK", elapsed()

    except subprocess.TimeoutExpired:
        cleanup()
        return run_id, False, f"Timeout en {elapsed():.0f} min", elapsed()
    except Exception as e:
        cleanup()
        return run_id, False, str(e)[:200], elapsed()



if __name__ == "__main__":

    if not NEW_RUNS_FILE.exists() or NEW_RUNS_FILE.stat().st_size == 0:
        log("new_runs.txt vacío o inexistente. Ejecutar primero update_01_fetch_new.py")
        exit(0)

    pending = [r.strip() for r in NEW_RUNS_FILE.read_text().splitlines() if r.strip()]

    log("=" * 60)
    log(f"TB-PROFILER: ACTUALIZACIÓN")
    log(f"Runs a procesar : {len(pending)}")
    log(f"Workers         : {N_WORKERS}")
    log(f"Disco libre     : {disk_free_gb():.1f} GB")
    log("=" * 60)

    overall_start = time.time()
    ok_count = 0
    fail_count = 0
    failed_runs = []

    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        futures = {executor.submit(process_sample, sid): sid for sid in pending}
        for i, future in enumerate(as_completed(futures), 1):
            run_id, success, msg, mins = future.result()
            status = "NO" if success else "YES"
            log(f"[{i}/{len(pending)}] {run_id} {status} {mins:.1f} min  {'' if success else msg}")
            if success:
                ok_count += 1
            else:
                fail_count += 1
                failed_runs.append((run_id, msg))

    elapsed_h = (time.time() - overall_start) / 3600
    log("=" * 60)
    log(f"COMPLETADO en {elapsed_h:.2f} horas")
    log(f"  Procesados : {ok_count}")
    log(f"  Fallidos   : {fail_count}")
    if failed_runs:
        log("Runs fallidos (se marcarán en Neo4j pero no bloquean el pipeline):")
        for rid, err in failed_runs:
            log(f"  {rid}: {err[:100]}")
    log(f"JSONs nuevos guardados en   : {JSON_CACHE}")
    log("=" * 60)