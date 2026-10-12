#!/usr/bin/env python3
"""Run each catalog entry's standard-library correctness tests in isolation."""
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
catalog = json.loads((root / "counter-measures/catalog.json").read_text())["counter_measures"]
for entry in catalog:
    tests = root / entry["path"] / "tests"
    if not tests.is_dir():
        raise RuntimeError("missing correctness tests for " + entry["id"])
    print("Checking " + entry["id"], flush=True)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(tests), "-v"], check=True)
