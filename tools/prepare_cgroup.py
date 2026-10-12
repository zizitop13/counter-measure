#!/usr/bin/env python3
"""Create an empty cgroup-v2 subtree for equal per-handler memory budgets."""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--parent", type=Path, required=True)
args = parser.parse_args()
root = Path("/sys/fs/cgroup")
parent = args.parent.resolve()
if parent.parent != root or not parent.name.startswith("counter-measure-"):
    parser.error("parent must be /sys/fs/cgroup/counter-measure-<run-id>")
if "memory" not in (root / "cgroup.controllers").read_text().split():
    raise RuntimeError("cgroup v2 memory controller is required")
if "memory" not in (root / "cgroup.subtree_control").read_text().split():
    (root / "cgroup.subtree_control").write_text("+memory")
parent.mkdir()
(parent / "cgroup.subtree_control").write_text("+memory")
print(parent)
