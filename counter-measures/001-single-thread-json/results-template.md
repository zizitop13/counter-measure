# Results — counter-measure 001

Source commit: `<SHA>` · UTC run time: `<timestamp>` · CI run: `<URL or local>`

| Control | Value |
|---|---|
| CPython exact version/build | `3.15.0`, default GIL; `<sys.version / CONFIG_ARGS>` |
| JDK exact version/build/vendor | `27+35`, `<vendor>` |
| JVM flags | `-XX:+UseZGC -Xms64m -Xmx1536m -XX:ActiveProcessorCount=1 -XX:ConcGCThreads=1 -XX:ParallelGCThreads=1 -Xlog:gc*:file=<path>:uptime,level,tags:filecount=0` |
| CPU model, OS, kernel | `<hardware / OS>` |
| Handler / generator / orchestrator CPU | `<core IDs and physical topology>` |
| Filesystem | `<type and mount>` |
| Memory budget / enforcement | `<MiB / cgroup or sampled RSS guard>` |
| Java heap maximum | `<MiB>`; CPython has no equivalent Xmx |
| Payload / window / flush / writer buffer | `<bytes / count / N / bytes>` |
| Warm-up / measurement / repetitions | `<seconds / seconds / at least 5>` |
| Fixed offered rate / retention / allocation rounds | `<msg/s / nodes / passes>` |

Copy rows for A (short-lived), B (allocation pressure), C (retained cycles), and **both** unlimited and fixed-rate modes. All latency fields are milliseconds. Each aggregate cell is `median [min–max]; IQR`. Do not insert smoke results or hypothetical numbers.

| Scenario | Mode | Runtime | Runs | Throughput msg/s | p50 ms | p90 ms | p99 ms | p99.9 ms | max ms | Handler CPU % | Handler CPU s | Measured peak RSS MiB | Lifetime HWM MiB | Generator CPU % | Generator peak RSS MiB |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | unlimited | CPython | 5+ | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` |
| A | unlimited | Java ZGC | 5+ | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` | `<measure>` |

| Scenario | Mode | Runtime | GC cycles | Pause count | Pause total ms | Pause p99 ms | Pause max ms | Allocation stall count / total ms | Retained / evicted | Completed messages | Output bytes | cgroup peak MiB | Observations |
|---|---|---|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---|
| A | unlimited | CPython | `<measure>` | `<measure>` | `<measure>` | `<measure or —>` | `<measure or —>` | n/a | `<counts>` | `<count>` | `<bytes>` | `<measure or n/a>` | `<observations>` |
| A | unlimited | Java ZGC | `<measure>` | `<measure>` | `<measure>` | `<measure or —>` | `<measure or —>` | `<count / total>` | `<counts>` | `<count>` | `<bytes>` | `<measure or n/a>` | `<observations>` |

Attach every measured run's individual metrics, percentile distributions, `gc.callbacks` events and `gc.get_stats()` before/after/delta, unmodified `-Xlog:gc*` logs, resource samples, effective commands, execution order, and validated counts. Use `—` for undefined pause percentiles when zero pauses were observed. Reference-count destruction and concurrent ZGC work are included in process CPU/latency but are not stop-the-world pause entries. Record generator saturation, fixed-rate admission backlog, warm-up sufficiency, and whether C actually evicted any cycles.
