# Working on counter-measures

## Repository organization

- Each comparison lives under `counter-measures/NNN-descriptive-topic/` with its README, version/config manifest, implementations in language folders, a runner, results template, and correctness tests.
- Register comparisons in `counter-measures/catalog.json`; the `path` and `runner` fields are repository-relative. Keep IDs stable and unique.
- Use the shared `tools/benchmarks.py`, `tools/check.py`, report generator, and result store. Workload-specific behavior belongs to its comparison folder.
- Keep generated metrics and large outputs out of `main`. The workflow replaces the latest selected results on `benchmark-results`; it preserves other topics' results.

## Measurement rules

- Verify stable runtime releases from their publishers; pin exact builds and record effective commands. Do not silently substitute older, early-access, or free-threaded runtimes.
- Never fabricate numbers or present smoke tests as performance conclusions.
- Check functional equivalence before measurement and count/check output records after the timed interval.
- Keep at least five fresh-process measured runs per cell. Warm up inside each measured process. Randomize paired execution order and keep paired languages on one machine, the same core allocation, and the same filesystem.
- Define acknowledgement, throughput interval, percentile method, backpressure, and memory accounting explicitly. Preserve all latency samples for calculating exact percentiles.
- Include load-generator cost, CPU affinity, GC observations, and resource limits in evidence. CPU includes runtime background threads.
- Keep warm-up and shutdown cleanup out of reported GC intervals; final buffered output flush belongs to completion throughput. Separate GC pauses, concurrent GC work, and allocation stalls.
- Use only the standard library for comparison 001, including tests and reporting. Build toolchains and GitHub Actions setup steps are infrastructure, not measured dependencies.

## Schema v1

`results.json` contains `schema_version: 1`, `counter_measure`, `title`, `status: "complete"`, `smoke`, `created_at` (UTC), `environment`, `settings`, `runs`, and `aggregates`.

Each run has a stable `name`, `scenario`, `mode`, `language`, `repeat`, `execution_order`, `metrics`, actual completed `count`, `warnings`, and effective `command`. Comparison 001 also stores full generator/handler metrics, GC events, cgroup peak, and validated output bytes. Keep raw GC logs and sampled resource data in the workflow evidence artifact.

Each aggregate contains `scenario`, `mode`, `language`, `runs`, `warnings`, and `metrics`. Each metric has `median`, `min`, `max`, and `iqr` across **per-run measurements**; do not pool per-message latencies across independent runs. Missing observations use JSON `null`; no observed pause has count/total zero and undefined percentile/max.

Common metric names: `throughput_mps`, `latency_p50_ms`, `latency_p90_ms`, `latency_p99_ms`, `latency_p99.9_ms`, `latency_max_ms`, `handler_cpu_percent`, `handler_cpu_seconds`, `peak_rss_mib`, `lifetime_peak_rss_mib`, `generator_cpu_percent`, `generator_peak_rss_mib`, `gc_pause_count`, `gc_pause_total_ms`, `gc_pause_p99_ms`, `gc_pause_max_ms`, `gc_collections`, `allocation_stall_count`, `allocation_stall_total_ms`, `retained`, `evicted`.

The shared index uses the catalog. Comparison 001 has a workload-specific detailed view; other comparisons receive a generic metric view until a matching renderer is added. Extend schema/reporting deliberately when a new topic needs other measurements. Do not relabel another language as Java or another workload as TCP JSON processing.

## Validation

Run `python3.15 tools/check.py` and `python3.15 tools/benchmarks.py --smoke --delete-output`. Inspect rendered HTML and full metrics. For changes that affect timings or fairness, run the appropriate full repeated benchmark. Do not add tests that merely mirror implementation internals; test protocol, outcomes, failure handling, and metric definitions.
