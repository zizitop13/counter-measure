#!/usr/bin/env python3
"""Keep one latest result per topic on a separate Git branch; no growing UI archive."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "benchmark-results"


def git(*args, cwd=ROOT, **kwargs):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, **kwargs)


def fetch_store():
    remote = git("ls-remote", "--heads", "origin", BRANCH, capture_output=True).stdout.strip()
    if not remote:
        return False
    git("fetch", "--no-tags", "origin", f"refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}")
    return True


def restore(results_root):
    if not fetch_store():
        return
    entries = json.loads((ROOT / "counter-measures/catalog.json").read_text())["counter_measures"]
    for entry in entries:
        stored = subprocess.run(["git", "show", f"origin/{BRANCH}:data/{entry['id']}.json"], cwd=ROOT,
                                capture_output=True, text=True)
        if stored.returncode:
            continue  # A newly added topic has no result yet.
        data = json.loads(stored.stdout)
        if data.get("counter_measure") != entry["id"] or data.get("status") != "complete" or data.get("smoke"):
            raise RuntimeError("stored result identity or status is invalid")
        destination = results_root / entry["id"]
        destination.mkdir(parents=True, exist_ok=True)
        (destination / ".counter-measure-output").write_text(entry["id"] + "\n")
        (destination / "results.json").write_text(stored.stdout)


def publish(results_root, site):
    exists = fetch_store()
    with tempfile.TemporaryDirectory(prefix="counter-measure-store-") as temporary:
        worktree = Path(temporary) / "store"
        git("worktree", "add", "--detach", str(worktree), f"origin/{BRANCH}" if exists else "HEAD")
        try:
            if not exists:
                git("switch", "--orphan", BRANCH, cwd=worktree)
            data_dir = worktree / "data"
            data_dir.mkdir(exist_ok=True)
            for result in results_root.glob("*/results.json"):
                data = json.loads(result.read_text())
                if data.get("status") != "complete" or data.get("smoke"):
                    raise ValueError("only complete measured results may be persisted")
                shutil.copy2(result, data_dir / (data["counter_measure"] + ".json"))
            if not (site / ".counter-measure-site").is_file():
                raise ValueError("expected generated report site")
            for path in site.iterdir():
                if path.name == ".counter-measure-site": continue
                target = worktree / path.name
                if target.is_dir(): shutil.rmtree(target)
                elif target.exists(): target.unlink()
                if path.is_dir(): shutil.copytree(path, target)
                else: shutil.copy2(path, target)
            git("add", "--all", cwd=worktree)
            changed = git("status", "--porcelain", cwd=worktree, capture_output=True).stdout
            if not changed:
                return
            git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                "commit", "-m", "Replace latest counter-measure results", cwd=worktree)
            git("push", "origin", f"HEAD:refs/heads/{BRANCH}", cwd=worktree)
        finally:
            git("worktree", "remove", "--force", str(worktree))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["restore", "publish"])
    parser.add_argument("--results-root", type=Path, default=ROOT / "results/latest")
    parser.add_argument("--site", type=Path, default=ROOT / "results/latest/site")
    args = parser.parse_args()
    if args.operation == "restore": restore(args.results_root.resolve())
    else: publish(args.results_root.resolve(), args.site.resolve())
