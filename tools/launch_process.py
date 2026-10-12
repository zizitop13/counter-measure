#!/usr/bin/env python3
"""Set affinity and optionally join an already configured cgroup before exec."""
import argparse
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--cpu", type=int, required=True)
parser.add_argument("--cgroup", type=Path)
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
command = args.command[1:] if args.command[:1] == ["--"] else args.command
if not command:
    parser.error("missing command after --")
os.sched_setaffinity(0, {args.cpu})
if args.cgroup:
    (args.cgroup / "cgroup.procs").write_text(str(os.getpid()))
os.execvpe(command[0], command, os.environ)
