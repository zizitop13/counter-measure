#!/usr/bin/env python3
"""Catalog-driven entry point; replaces only selected generated outputs."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from report import build_report

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--counter-measure", default="all")
parser.add_argument("--results-root", type=Path, default=ROOT / "results/latest")
args, remaining = parser.parse_known_args()
if remaining[:1] == ["--"]: remaining.pop(0)
catalog = json.loads((ROOT / "counter-measures/catalog.json").read_text())["counter_measures"]
selected = catalog if args.counter_measure == "all" else [entry for entry in catalog if entry["id"] == args.counter_measure]
if not selected: parser.error("unknown counter-measure")
if "--output" in remaining: parser.error("use --results-root with this entry point")
results_root = args.results_root.resolve()
for entry in selected:
    destination = results_root / entry["id"]
    if destination.exists():
        marker = destination / ".counter-measure-output"
        if not marker.is_file() or marker.read_text().strip() != entry["id"]:
            raise RuntimeError("refusing to replace output without its generated-output marker")
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    (destination / ".counter-measure-output").write_text(entry["id"] + "\n")
    subprocess.run([sys.executable, str(ROOT / entry["path"] / entry["runner"]),
                    "--output", str(destination)] + remaining, check=True)
build_report(results_root, results_root / "site", allow_smoke="--smoke" in remaining)
print("Report: " + str(results_root / "site/index.html"))
