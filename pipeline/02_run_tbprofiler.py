#!/usr/bin/env python3
"""
Step 2 - Run TB-Profiler on the new SRA runs.

  1. Read the run IDs from new_runs.txt
  2. Download each run from SRA (prefetch + fasterq-dump, fastq-dump as fallback)
  3. Run TB-Profiler and validate the result (QC block, software and database version)
  4. Save the JSON results to json_cache/ and the failed runs to failed_samples.csv

Usage: python pipeline/02_run_tbprofiler.py
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# --- Configuration ---
WORKDIR       = Path.home() / "workdir"
JSON_CACHE    = Path.home() / "json_cache"
NEW_RUNS_FILE = Path.home() / "new_runs.txt"
LOG_FILE      = Path.home() / "run_tbprofiler_update.log"
FAILED_FILE   = Path.home() / "failed_samples.csv"

N_WORKERS    = 2        # runs processed in parallel
TIMEOUT_DL   = 3600     # seconds: SRA download
TIMEOUT_FQ   = 1800     # seconds: FASTQ conversion
TIMEOUT_PROF = 10800    # seconds: TB-Profiler
MIN_DISK_GB  = 5

# All samples must be profiled with the same TB-Profiler and tbdb versions as the
# historical results (June 2025 run), otherwise resistance calls are not comparable.
# Change these only when ALL samples are re-processed with the new versions.
EXPECTED_TBPROFILER_VERSION = "6.6.6"
EXPECTED_DB_COMMIT          = "0a909094"   # tbdb commit, 5 Aug 2025


# --- Helpers ---
def log(msg):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def disk_free_gb():
    st = os.statvfs(WORKDIR)
    return (st.f_bavail * st.f_frsize) / 1e9


def find_json(wdir, run_id):
    """TB-Profiler's output folder differs between versions; check the known locations."""
    candidates = [
        os.path.join(wdir, "results", "results", f"{run_id}.results.json"),
        os.path.join(wdir, "results", f"{run_id}.results.json"),
        os.path.join(wdir, f"{run_id}.results.json"),
        os.path.join(Path.home(), "results", f"{run_id}.results.json"),
    ]
    return next((p for p in candidates if os.path.exists(p)), None)


def process_sample(run_id):
    """Download and profile one run. Returns (run_id, success, message, minutes)."""
    start    = time.time()
    wdir     = str(WORKDIR / run_id)
    r1       = os.path.join(wdir, f"{run_id}_1.fastq.gz")
    r2       = os.path.join(wdir, f"{run_id}_2.fastq.gz")
    sra_dir  = f"/tmp/{run_id}"
    sra_file = os.path.join(sra_dir, f"{run_id}.sra")

    def elapsed():
        return (time.time() - start) / 60

    def cleanup():
        shutil.rmtree(wdir, ignore_errors=True)
        shutil.rmtree(sra_dir, ignore_errors=True)

    try:
        if disk_free_gb() < MIN_DISK_GB:
            return run_id, False, f"Disk full ({disk_free_gb():.1f} GB free)", elapsed()

        shutil.rmtree(wdir, ignore_errors=True)
        os.makedirs(wdir, exist_ok=True)

        # Download with prefetch, then convert to FASTQ
        shutil.rmtree(sra_dir, ignore_errors=True)
        r = subprocess.run(
            ["prefetch", "--max-size", "50G", "--output-directory", "/tmp", run_id],
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

        # Fallback: fastq-dump straight from SRA
        if not os.path.exists(r1):
            r = subprocess.run(
                ["fastq-dump", "--split-files", "--gzip", "--outdir", wdir, run_id],
                capture_output=True, text=True, timeout=TIMEOUT_DL)
            if r.returncode != 0:
                cleanup()
                return run_id, False, f"Download failed: {r.stderr[:200]}", elapsed()

        # Single-end runs produce <run>.fastq.gz; rename it to the read-1 name
        r1_se = os.path.join(wdir, f"{run_id}.fastq.gz")
        if os.path.exists(r1_se) and not os.path.exists(r1):
            os.rename(r1_se, r1)
        if not os.path.exists(r1):
            cleanup()
            return run_id, False, "FASTQ not found after download", elapsed()

        paired      = os.path.exists(r2)
        results_dir = os.path.join(wdir, "results")
        os.makedirs(results_dir, exist_ok=True)

        # Run TB-Profiler
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
            err = r.stderr[-300:] if r.stderr else "JSON not found"
            cleanup()
            return run_id, False, f"TB-Profiler: {err}", elapsed()

        # Validate the JSON: QC block present and expected software/database versions
        try:
            with open(json_src) as jf:
                d = json.load(jf)
            if "qc" not in d:
                cleanup()
                return run_id, False, "JSON has no qc field", elapsed()
            pipeline_info = d.get("pipeline", {})
            version   = pipeline_info.get("software_version", "")
            db_commit = (pipeline_info.get("db_version") or {}).get("commit", "")
            if version != EXPECTED_TBPROFILER_VERSION or not db_commit.startswith(EXPECTED_DB_COMMIT):
                cleanup()
                return (run_id, False,
                        f"Version mismatch: TB-Profiler {version}, tbdb {db_commit} "
                        f"(expected {EXPECTED_TBPROFILER_VERSION}, {EXPECTED_DB_COMMIT})",
                        elapsed())
        except Exception as e:
            cleanup()
            return run_id, False, f"Invalid JSON: {e}", elapsed()

        # Save the result
        shutil.copy2(json_src, JSON_CACHE / f"{run_id}.results.json")
        cleanup()
        return run_id, True, "OK", elapsed()

    except subprocess.TimeoutExpired:
        cleanup()
        return run_id, False, f"Timeout after {elapsed():.0f} min", elapsed()
    except Exception as e:
        cleanup()
        return run_id, False, str(e)[:200], elapsed()


# --- Main ---
def main():
    WORKDIR.mkdir(exist_ok=True)
    JSON_CACHE.mkdir(exist_ok=True)

    if not NEW_RUNS_FILE.exists() or NEW_RUNS_FILE.stat().st_size == 0:
        log("new_runs.txt is empty or missing. Run pipeline/01_fetch_ncbi.py first.")
        sys.exit(0)

    pending = [r.strip() for r in NEW_RUNS_FILE.read_text().splitlines() if r.strip()]

    log("=" * 60)
    log("TB-PROFILER: UPDATE")
    log(f"Runs to process : {len(pending)}")
    log(f"Workers         : {N_WORKERS}")
    log(f"Free disk       : {disk_free_gb():.1f} GB")
    log("=" * 60)

    overall_start = time.time()
    ok_count    = 0
    failed_runs = []

    with ProcessPoolExecutor(max_workers=N_WORKERS) as executor:
        futures = {executor.submit(process_sample, run_id): run_id for run_id in pending}
        for i, future in enumerate(as_completed(futures), 1):
            run_id, success, msg, mins = future.result()
            status = "OK" if success else "FAIL"
            log(f"[{i}/{len(pending)}] {run_id} {status} {mins:.1f} min  {'' if success else msg}")
            if success:
                ok_count += 1
            else:
                failed_runs.append((run_id, msg))

    elapsed_h = (time.time() - overall_start) / 3600
    log("=" * 60)
    log(f"COMPLETED in {elapsed_h:.2f} hours")
    log(f"  Processed : {ok_count}")
    log(f"  Failed    : {len(failed_runs)}")
    if failed_runs:
        log("Failed runs (recorded in Neo4j; they do not stop the pipeline):")
        for run_id, err in failed_runs:
            log(f"  {run_id}: {err[:100]}")

    # Save failed runs so 04_load_neo4j.py can record them in Neo4j
    with open(FAILED_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["run_id", "error"])
        writer.writerows(failed_runs)
    log(f"Failed runs saved to : {FAILED_FILE}")
    log(f"New JSONs saved to   : {JSON_CACHE}")
    log("=" * 60)


if __name__ == "__main__":
    main()
