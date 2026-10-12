# 001 — one-thread TCP JSON processing

Compare **CPython 3.15.0, default GIL build**, and **Temurin OpenJDK 27+35, ZGC** on one application thread. These were the latest stable feature releases verified on **2026-10-12**: [Python release](https://www.python.org/downloads/release/python-3150/), [JDK release notes and build](https://www.oracle.com/java/technologies/javase/27all-relnotes.html). Versions are pinned in [config.json](config.json); update pins intentionally for a new comparison, rather than making old runs depend on “latest.”

## Identical behavior and execution model

Both implementations use **one blocking application thread**, one active connection at a time, and a TCP listen backlog. They accept sequential client connections; additional connections wait while the active connection is serviced. The benchmark uses one persistent, pipelined connection. There is no selector implementation advantage, application pool, asynchronous file writer, or per-connection worker. Runtime-created JVM compiler and GC threads still exist; they share the handler's one-core CPU affinity, and their CPU is included.

Every NDJSON input line is strictly decoded as UTF-8, parsed into a generic JSON tree, and transformed in the same order:

1. Set `processed_ts` to Unix epoch **milliseconds**.
2. Calculate `notional = float(qty) * float(price)` using IEEE-754 binary64.
3. Uppercase the ASCII `symbol`.
4. Serialize compact UTF-8 JSON and append a newline to the buffered file writer.
5. Increment the processed count; flush every `--flush-every N` messages.
6. Return the input `id` as an ASCII decimal line to acknowledge completion.

Both use a **65,536-byte file buffer**, configurable with `--buffer-bytes`. Flush sends buffered bytes to the operating system; neither handler requests fsync. On graceful `{"_control":"stop"}`, flush the tail, return the final metrics/count, print the same metrics to stdout, and exit. Direct handler use appends to existing files.

For benchmark warm-up only, `{"_control":"begin"}` closes/truncates the warm-up output, clears retained state, performs an explicit collection **outside measurement**, resets counters and GC observations, and begins measurement in the same process. Java keeps JIT-compiled code. All warm-up observations are retained separately but excluded from measured aggregates. Explicit collection is never requested during the measured data path.

The protocol's shared domain is JSON objects with a nonnegative integer `id`, integer `qty`, finite numeric `price`, and ASCII string `symbol`. Integers in all fields must be within ±(2⁵³−1); nesting is limited to 64; unpaired Unicode surrogates, malformed UTF-8, NaN/infinity, notional overflow, and lines over 1 MiB are rejected. Other fields, arrays, nested objects, nulls, booleans, escaped strings, and valid Unicode text are preserved. Duplicate keys use last-value-wins in both parsers. `_control` is reserved. Quantity and notional here are binary floating point benchmark values, not a decimal-money calculation.

Output is **functionally equivalent JSON**, not promised byte-identical: timestamps differ and valid floating-point textual spellings can differ. Equivalence tests compare parsed values. Actual output bytes are recorded so differences cannot silently alter the I/O interpretation. The JDK contains no standard JSON parser; `Handler.java` includes a generic parser/serializer using only standard-library classes. CPython uses its standard `json` module and C acceleration. This is a practical comparison under the requested dependency restriction, not a universal proof about language speed.

## Build and run individual handlers

From this directory, use the pinned toolchains on `PATH`. Choose allowed, different physical CPU cores for handler and loader; the full harness discovers them automatically. The examples use CPUs 2 and 3.

Python:

```bash
taskset -c 2 python3.15 -I python/handler.py \
  --port 9000 --output /tmp/python-messages.ndjson \
  --scenario A --flush-every 256 --buffer-bytes 65536
```

Java build and **complete JVM flags** for the default benchmark profile:

```bash
mkdir -p build
javac --release 27 -d build java/Handler.java
taskset -c 2 java \
  -XX:+UseZGC -Xms64m -Xmx1536m \
  -XX:ActiveProcessorCount=1 -XX:ConcGCThreads=1 -XX:ParallelGCThreads=1 \
  -Xlog:gc*:file=/tmp/java-gc.log:uptime,level,tags:filecount=0 \
  -cp build Handler --port 9000 --output /tmp/java-messages.ndjson \
  --scenario A --flush-every 256 --buffer-bytes 65536
```

In a second terminal, use the **same separate-process Python generator** for either handler. It ends the server gracefully itself:

```bash
taskset -c 3 python3.15 -I load_generator.py \
  --port 9000 --warmup 10 --duration 10 --rate 0 \
  --payload-bytes 256 --window 1024 --scenario A \
  --output /tmp/load-result.json
```

`--rate 0` means unlimited; a positive rate schedules that many arrivals each second. `--payload-bytes` includes the trailing newline; each input message has exactly that size. An extra `pad` field supplies padding. The generator uses fixed-width integer IDs and a reusable template, avoiding repeated JSON construction in the timed client path. `--window` limits queued/unacknowledged messages. It checks every returned ID. `--save-latencies` additionally saves native-endian uint64 nanosecond samples; percentiles always use all messages regardless of this option.

## Run the fair matrix

From the repository root:

```bash
python3.15 tools/benchmarks.py --counter-measure 001-single-thread-json \
  --runs 5 --warmup 10 --duration 10 \
  --payload-bytes 256 --rate 10000 --window 1024 \
  --flush-every 256 --buffer-bytes 65536 \
  --heap-mib 1536 --memory-limit-mib 3072 \
  --retain 1000000 --allocation-rounds 8 --delete-output
```

The dispatcher replaces the prior generated directory for this counter-measure, runs both languages, and creates `results/latest/site/index.html`, topic HTML, `results.json`, and `summary.md`. The directly callable local runner is `counter-measures/001-single-thread-json/run_benchmarks.py`; it requires a fresh `--output` directory. Keep output NDJSON by omitting `--delete-output`; when enabled, deletion follows full validation outside the timed interval.

Every scenario gets **five runs per language per load mode**. Each run launches a fresh handler process and fresh generator. Handler CPU affinity stays identical across languages and covers all JVM background threads. The generator has a separate physical core. The orchestrator uses a third physical core if available, otherwise shares the generator core. All pairs run sequentially on one machine and the same output filesystem. Seeded randomization varies cell and language order within each repetition. Effective commands, order, CPUs, kernel, filesystem, exact runtime build/configuration, source commit, and CI run ID are stored.

| Scenario | Common workload | State lifetime |
|---|---|---|
| A | Parse, transform, serialize, append | Message trees become unreachable after handling |
| B | A plus `allocation_rounds` additional parse/serialize passes; keep intermediate trees/byte strings through the message | Extra structures become unreachable after handling; a Java volatile sink prevents allocation elimination |
| C | A plus a ring of message nodes; each node has a peer whose `owner` points back to the node | Grow to `retain`, then evict the oldest graph; evicted cycles become collectible |

Scenario B also uses nested arrays in the common input payload. Its minimum payload size is checked by the generator. C's default cap is one million, but a timed run may finish before reaching it. The report shows actual retained and evicted counts; no eviction means a live-heap scan/growth test rather than an unreachable-cycle reclamation test. To force reclamation in a shorter run, use `--retain 10000`. Fixed-rate runs deliver the same scheduled number to both languages; unlimited runs can retain different counts because their capacities differ.

## Metric definitions

| Metric | Definition |
|---|---|
| Throughput | Successfully acknowledged count / wall time from measured phase start through all acknowledgements, queue drain, STOP response and final buffered flush; excludes warm-up and percentile sorting |
| p50, p90, p99, p99.9, max latency | Nearest-rank percentiles over **every** acknowledged message; compute each run first, then summarize independent runs |
| Unlimited latency | Time from admission to the loader's bounded buffer until acknowledgement reception; includes pipelining queueing and transport |
| Fixed-rate latency | Time from the scheduled arrival to acknowledgement reception, including client admission backlog; also report admission and wire-latency percentiles |
| Handler CPU | Process CPU time delta over the measurement, including GC/JIT/runtime threads; report seconds and percentage of one core over completion wall time |
| Peak RSS | Maximum `/proc/PID/status` VmRSS sample in measurement, sampled every 20 ms; report lifetime VmHWM separately because it includes warm-up/startup |
| Generator cost | Separate-process CPU seconds/percentage and sampled peak RSS; flag ≥85% CPU as potential generator saturation |
| Python GC | `gc.callbacks` start/stop durations during measurement; record `gc.get_stats()` before/after and per-generation collection/collected/uncollectable deltas |
| Java GC | Parse timed stop-the-world `Pause ... Nms` lines from `-Xlog:gc*`, filtered to the measured JVM-uptime interval; report full events, count, total and percentiles |
| Allocation stalls | ZGC log entries parsed separately from pauses; concurrent cycle durations are never reported as pause times |
| Spread | Median, minimum, maximum, and inclusive IQR across per-run values; HTML/Markdown show median and range, JSON includes IQR for every metric |

Fixed-rate runs never skip arrivals when the window fills: they continue sending the scheduled finite sequence and report the additional drain time. That avoids hiding overload through coordinated omission. Scheduling and client CPU are still finite; p99 admission lag over 5 ms is flagged. Acknowledgement receive times include client scheduling delay. Use unlimited mode to compare capacity and a fixed rate below **both** capacities to compare latency at equal load. Saturated-window latency is not intrinsic parse time.

The runner checks every output record's ID/order, uppercase symbol, notional and processed timestamp, and requires file count = handler count = acknowledged count. Validation is outside timing. Failure aborts the report and leaves diagnostics; no incomplete result is published. Warm-up completion counts and per-second completion series are retained; fewer than 10,000 warm-up messages produces a warning. A fixed duration is not proof that compilation has stopped: increase warm-up and examine rate stability/spread for close decisions.

## Memory limits and fairness caveats

CPython has no direct equivalent to `-Xmx`. Java uses a configurable heap maximum (default 1536 MiB), leaving room for non-heap memory inside a **common 3072 MiB process budget**. On CI, both handlers run in their own cgroup v2 with identical `memory.max` and zero swap. Cgroup usage also includes charged page cache; its peak is retained separately. The cgroup is entered before exec so runtime allocations are charged consistently. The handler RSS guard is additional; it is not a hard heap limit. Local runs without `--cgroup-parent` use only the sampled RSS guard and label this explicitly. `RLIMIT_AS` is deliberately avoided because ZGC reserves much more virtual address space than its physical heap.

| Caveat | Control / remaining limit |
|---|---|
| JIT warm-up and adaptive compilation | Warm-up the actual scenario in the same process; discard its output/state; repeat from fresh processes; retain per-second rates and warn on insufficient messages. Increase warm-up for stability checks. |
| GC tuning and hidden cores | Explicit ZGC, one GC worker of each type, one CPU affinity for the entire handler; CPython's default collector remains enabled. Record flags/stats and all process CPU. |
| Reference counting vs tracing GC | Python callback pauses exclude reference-count destruction. CPU and end-to-end latency include it. Do not compare callback totals as all memory-management overhead. |
| Buffering and filesystem | Equal buffer size, flush cadence, same filesystem, completion boundary, no fsync. Record actual output bytes. Results include serialization, transport, file buffer copies and page-cache behavior. |
| Standard-library and runtime implementation | Python's JSON C implementation vs included Java parser, different string/map/number layouts and syscall paths; cross-language semantic tests preserve the common contract. This does not isolate arithmetic alone. |
| Generator bottleneck and pipelining | Separate physical core, reusable payload template, bounded window, CPU/RSS observations and saturation flags; no numerical correction of generator-limited results. |
| Retained population and heap budget | Common total-process budget where supported, explicit Java heap, actual live/evicted counts. Use equal fixed-rate counts for population comparisons; memory layouts cannot be made identical. |
| CI host variation | Both languages run on one host in randomized pairs, with exact hardware metadata and spread. GitHub-hosted VMs are shared infrastructure; use a stable dedicated Linux host for small differences. |

The [results template](results-template.md) contains every requested metric. The HTML exposes detailed per-run measurements and raw JSON; `benchmark-evidence` adds the unmodified GC logs, stderr/stdout and resource samples. Reported numbers belong to their exact workload/configuration/hardware, rather than to every “single-threaded task.”
