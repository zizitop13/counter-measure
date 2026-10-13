# Counter-measure

Reproducible performance comparisons of languages, runtimes, and implementation choices. Each **counter-measure** owns its workload and correctness checks; shared tools run the catalog and publish the latest measured results.

| Counter-measure | Question | Runtimes | Reproduce |
|---|---|---|---|
| [001 — one-thread TCP JSON processing](counter-measures/001-single-thread-json/README.md) | How do CPython and Java ZGC compare when one application thread parses, transforms, and writes messages? | CPython **3.15.0**, default GIL; Temurin JDK **27+35**, ZGC | `python3.15 tools/benchmarks.py` |

[Latest HTML report](https://zizitop13.github.io/counter-measure/) · [Benchmark workflow](https://github.com/zizitop13/counter-measure/actions/workflows/benchmarks.yml)

## LLM code-clarity experiments

Separate from runtime performance counter-measures, [`llm-benchmarks/`](llm-benchmarks/README.md) contains controlled, functionally equivalent code variants for experiments on LLM comprehension and modification cost. The first experiment compares nested conditionals with guard clauses in a synthetic Forex liquidity-path domain and is intended for manual local runs with LM Studio.

## Run locally

Use Linux with CPython 3.15.0 and JDK 27+35 on `PATH`. The harness checks exact versions and rejects free-threaded Python. There are no application or benchmark package dependencies.

```bash
python3.15 tools/check.py
python3.15 tools/benchmarks.py
python3.15 -m http.server 8000 --directory results/latest/site
```

Open `http://localhost:8000`. The default matrix runs three scenarios, two load modes, two languages, and five repetitions: **60 measured runs**. Allow roughly 20–30 minutes, depending on overload drain and GC. All language pairs run sequentially on the same machine; a matrix of separate GitHub runners would weaken the comparison.

The shell entry point also accepts an explicit worker interpreter:

```bash
./run_benchmarks --python python3.15
```

For a quick correctness check, use `python3.15 tools/benchmarks.py --smoke`. Smoke results are clearly labeled and cannot be published as benchmark evidence.

## GitHub Actions and Pages

The **Benchmarks and Pages** workflow runs automatically after relevant changes on `main`, or manually from the Actions tab. Manual inputs configure payload size, fixed offered rate, durations, retained-state capacity, repetitions, and catalog ID. Every measured cell requires at least five runs.

The workflow tests equivalence, installs pinned runtime builds, selects CPU affinity, enforces equal cgroup-v2 memory budgets, runs all pairs on one runner, validates every output record, and produces HTML, Markdown, JSON, GC logs, and resource samples. It uploads `benchmark-evidence` and publishes the HTML through GitHub Pages.

It replaces the previous result **for each selected topic**. The separate `benchmark-results` branch stores one current JSON result per topic plus the current site; old numbers do not accumulate in the site's UI. Other topics' latest results are restored before a partial run. Git history and workflow artifacts still provide provenance. Failed runs retain diagnostic artifacts and do not replace the last successful published result.

Pages enablement is attempted automatically. If repository policy prevents it, choose **Settings → Pages → Build and deployment → Source: GitHub Actions**, then re-run the workflow. No custom domain is needed.

## Add a counter-measure

```text
counter-measures/
  catalog.json
  001-single-thread-json/
    config.json
    README.md
    python/handler.py
    java/Handler.java
    load_generator.py
    run_benchmarks.py
    results-template.md
    tests/test_counter_measure.py
tools/
  benchmarks.py          # catalog dispatcher
  check.py               # catalog correctness checks
  report.py              # shared report generation
  result_store.py        # replace latest topic results
  launch_process.py      # affinity / cgroup before exec
  prepare_cgroup.py      # CI memory-controller preparation
```

Create `counter-measures/NNN-topic/`, add a catalog entry and a `run_benchmarks.py` accepting `--output`, and write meaningful correctness tests under `tests/`. Each runner must emit a **complete** `results.json` with schema version 1, its catalog ID, timestamp, exact environment, settings, individual runs, and per-cell aggregates. Shared tools never pretend failed or partial measurements are successful. See [AGENTS.md](AGENTS.md) for the result contract and extension rules. Install any additional language toolchains in the workflows as new comparisons are added.

Generated outputs are ignored in the source branch. The root runner replaces only directories carrying its generated-output marker. The [first counter-measure's README](counter-measures/001-single-thread-json/README.md) documents protocol semantics, metric definitions, commands, and fairness limits.
