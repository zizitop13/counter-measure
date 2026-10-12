#!/usr/bin/env python3
"""Linux benchmark orchestrator. Fresh processes, paired runs, common generator."""

import argparse
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import selectors
import shutil
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG = json.loads((HERE / "config.json").read_text())
DEFAULTS = CONFIG["defaults"]


def cpu_topology(cpu):
    base = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
    try:
        return (base.joinpath("physical_package_id").read_text().strip(),
                base.joinpath("core_id").read_text().strip())
    except OSError:
        return ("unknown", str(cpu))


def choose_cpus(handler_cpu=None, generator_cpu=None):
    allowed = sorted(os.sched_getaffinity(0))
    handler_cpu = allowed[0] if handler_cpu is None else handler_cpu
    if generator_cpu is None:
        generator_cpu = next((cpu for cpu in allowed if cpu != handler_cpu and
                              cpu_topology(cpu) != cpu_topology(handler_cpu)), None)
    if handler_cpu not in allowed or generator_cpu not in allowed or handler_cpu == generator_cpu:
        raise ValueError("two distinct allowed CPUs are required")
    if cpu_topology(handler_cpu) == cpu_topology(generator_cpu):
        raise ValueError("handler and generator must use different physical cores")
    return handler_cpu, generator_cpu


def proc_sample(pid):
    """RSS/HWM in KiB and CPU ticks; process stat includes all JVM threads."""
    try:
        status = Path(f"/proc/{pid}/status").read_text()
        stats = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        return None
    values = {key: int(value) for key, value in
              re.findall(r"^(VmRSS|VmHWM|Threads):\s+(\d+)", status, re.M)}
    values["cpu_seconds"] = (int(stats[11]) + int(stats[12])) / os.sysconf("SC_CLK_TCK")
    return values


def percentile_ms(samples):
    values = sorted(samples)
    if not values:
        return {key: None for key in ("p50", "p90", "p99", "p99.9", "max")}
    result = {name: values[max(0, math.ceil(len(values) * quantile) - 1)]
              for name, quantile in (("p50", .5), ("p90", .9), ("p99", .99), ("p99.9", .999))}
    result["max"] = values[-1]
    return result


def gc_metrics(language, handler, log):
    stalls = []
    if language == "python":
        events = handler["gc_events"]
        pauses = [event["pause_ms"] for event in events]
        collections = sum(entry["collections"] for entry in handler["gc_stats_delta"])
        kind = "CPython cyclic-GC callback durations (reference counting is excluded)"
    else:
        start, finish = handler["gc_window_start_uptime_ms"], handler["gc_window_end_uptime_ms"]
        events = []
        for line in log.read_text().splitlines():
            clock = re.search(r"\[([0-9.]+)s\]", line)
            if not clock or not start <= float(clock[1]) * 1000 <= finish:
                continue
            pause = re.search(r"GC\(\d+\)\s+(Pause .*?)\s+([0-9.]+)ms\s*$", line)
            if pause:
                events.append({"phase": pause[1], "pause_ms": float(pause[2])})
            stall = re.search(r"Allocation Stall.*?([0-9.]+)ms\s*$", line)
            if stall:
                stalls.append(float(stall[1]))
        pauses = [event["pause_ms"] for event in events]
        # Bean collection times include concurrent work. Pause times come ONLY from logs.
        collections = sum(max(0, after["collections"] - handler["gc_stats_before"][name]["collections"])
                          for name, after in handler["gc_stats_after"].items()
                          if "Cycles" in name)
        kind = "ZGC stop-the-world phases; concurrent cycles and allocation stalls are separate"
    return {"kind": kind, "pause_count": len(pauses), "pause_total_ms": sum(pauses),
            "pause_ms": percentile_ms(pauses), "collections": collections,
            "allocation_stall_count": len(stalls), "allocation_stall_total_ms": sum(stalls),
            "allocation_stall_max_ms": max(stalls, default=0), "events": events}


def spread(values):
    values = [value for value in values if value is not None]
    if not values:
        return {"median": None, "min": None, "max": None, "iqr": None}
    quartiles = statistics.quantiles(values, n=4, method="inclusive") if len(values) > 1 else [values[0]] * 3
    return {"median": statistics.median(values), "min": min(values), "max": max(values),
            "iqr": quartiles[2] - quartiles[0]}


def aggregate(runs):
    groups = {}
    for run in runs:
        key = (run["scenario"], run["mode"], run["language"])
        groups.setdefault(key, []).append(run)
    result = []
    fields = ["throughput_mps", "handler_cpu_percent", "handler_cpu_seconds", "peak_rss_mib",
              "lifetime_peak_rss_mib", "generator_cpu_percent", "generator_peak_rss_mib",
              "gc_pause_count", "gc_pause_total_ms", "gc_pause_max_ms", "gc_pause_p99_ms",
              "gc_collections", "allocation_stall_count", "allocation_stall_total_ms", "retained", "evicted"]
    fields += ["latency_" + q + "_ms" for q in ("p50", "p90", "p99", "p99.9", "max")]
    for (scenario, mode, language), members in groups.items():
        result.append({"scenario": scenario, "mode": mode, "language": language,
                       "runs": len(members), "metrics": {field: spread([run["metrics"][field] for run in members])
                                                           for field in fields},
                       "warnings": sorted({warning for run in members for warning in run["warnings"]})})
    return result


def launch(command, cpu, cgroup=None, **kwargs):
    prefix = [sys.executable, "-I", str(ROOT / "tools/launch_process.py"), "--cpu", str(cpu)]
    if cgroup:
        prefix += ["--cgroup", str(cgroup)]
    return subprocess.Popen(prefix + ["--"] + command, **kwargs)


def configure_cgroup(parent, name, memory_mib):
    if parent is None:
        return None
    group = parent / name
    group.mkdir()
    try:
        (group / "memory.max").write_text(str(memory_mib * 1024 * 1024))
        (group / "memory.swap.max").write_text("0")
    except OSError:
        group.rmdir()
        raise
    return group


def read_ready(process, timeout=60):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(timeout):
            raise TimeoutError("handler did not become ready")
        line = process.stdout.readline()
    ready = json.loads(line)
    if not ready.get("ready"):
        raise RuntimeError(f"unexpected readiness line {ready}")
    return ready


def run_one(args, language, scenario, mode, repeat, order, build, versions):
    name = f"{scenario}-{mode}-{repeat:02d}-{language}"
    directory = args.output / "raw" / name
    directory.mkdir(parents=True)
    output_file, gc_log = directory / "messages.ndjson", directory / "gc.log"
    common = ["--port", "0", "--output", str(output_file), "--scenario", scenario,
              "--flush-every", str(args.flush_every), "--buffer-bytes", str(args.buffer_bytes),
              "--retain", str(args.retain), "--allocation-rounds", str(args.allocation_rounds)]
    if language == "python":
        command = [args.python, "-I", str(HERE / "python/handler.py")] + common
    else:
        flags = ["-XX:+UseZGC", "-Xms64m", f"-Xmx{args.heap_mib}m", "-XX:ActiveProcessorCount=1",
                 "-XX:ConcGCThreads=1", "-XX:ParallelGCThreads=1",
                 f"-Xlog:gc*:file={gc_log}:uptime,level,tags:filecount=0"]
        command = [args.java] + flags + ["-cp", str(build), "Handler"] + common
    group = configure_cgroup(args.cgroup_parent, f"cm-{os.getpid()}-{name}", args.memory_limit_mib)
    handler = loader = None
    measuring = False
    rss_peak = generator_rss_peak = lifetime_hwm = max_threads = 0
    cgroup_peak = None
    samples = []
    result_path = directory / "load.json"
    start_wall = time.monotonic()
    print(f"{name}: warming up {args.warmup}s, measuring {args.duration}s", flush=True)
    with (directory / "handler.stderr").open("w") as handler_error, (directory / "load.stderr").open("w") as load_error:
        try:
            handler = launch(command, args.handler_cpu, group, stdout=subprocess.PIPE,
                             stderr=handler_error, text=True)
            ready = read_ready(handler)
            loader_command = [args.python, "-I", str(HERE / "load_generator.py"),
                              "--port", str(ready["port"]), "--duration", str(args.duration),
                              "--warmup", str(args.warmup), "--rate", str(args.rate if mode == "fixed" else 0),
                              "--payload-bytes", str(args.payload_bytes), "--window", str(args.window),
                              "--scenario", scenario, "--output", str(result_path)]
            if args.messages:
                loader_command += ["--messages", str(args.messages)]
            if args.save_latencies:
                loader_command += ["--save-latencies"]
            loader = launch(loader_command, args.generator_cpu, stdout=subprocess.PIPE,
                            stderr=load_error, bufsize=0)
            phase_buffer = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(loader.stdout, selectors.EVENT_READ)
                while loader.poll() is None:
                    for key, _ in selector.select(.02):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        phase_buffer.extend(chunk)
                        while b"\n" in phase_buffer:
                            line, _, rest = phase_buffer.partition(b"\n")
                            phase_buffer = bytearray(rest)
                            event = json.loads(line)
                            if event.get("phase") == "measurement": measuring = True
                            elif event.get("phase") == "finished": measuring = False
                    snapshot = proc_sample(handler.pid)
                    if snapshot:
                        lifetime_hwm = max(lifetime_hwm, snapshot.get("VmHWM", 0))
                        if snapshot.get("VmRSS", 0) > args.memory_limit_mib * 1024:
                            raise MemoryError(f"handler RSS exceeded {args.memory_limit_mib} MiB")
                        if measuring:
                            rss_peak = max(rss_peak, snapshot.get("VmRSS", 0))
                            max_threads = max(max_threads, snapshot.get("Threads", 0))
                            samples.append({"monotonic_ns": time.perf_counter_ns(),
                                            "rss_kib": snapshot.get("VmRSS", 0),
                                            "cpu_seconds": snapshot["cpu_seconds"]})
                    if measuring:
                        snapshot = proc_sample(loader.pid)
                        if snapshot: generator_rss_peak = max(generator_rss_peak, snapshot.get("VmRSS", 0))
                    if time.monotonic() - start_wall > args.run_timeout:
                        raise TimeoutError(f"run exceeded {args.run_timeout}s")
            if loader.wait() != 0:
                raise RuntimeError(f"load generator failed; see {directory / 'load.stderr'}")
            tail, _ = handler.communicate(timeout=30)
            (directory / "handler.stdout").write_text(json.dumps(ready) + "\n" + tail)
            if handler.returncode:
                raise RuntimeError(f"handler failed; see {directory / 'handler.stderr'}")
            if group:
                cgroup_peak = int((group / "memory.peak").read_text()) / 1048576
        finally:
            for process in (loader, handler):
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=30)
            if group: group.rmdir()
    if not result_path.exists():
        raise RuntimeError("generator did not produce metrics")
    data = json.loads(result_path.read_text())
    load, handler_metrics = data["load"], data["handler"]
    if language == "java" and not any("ZGC" in name for name in handler_metrics["gc_names"]):
        raise RuntimeError("JVM is not using ZGC")
    if not args.allow_other_versions and language == "java" and handler_metrics["java_version"] != CONFIG["java_version"]:
        raise RuntimeError("unexpected JDK build; benchmark version must be explicit")
    # Very short correctness runs can finish between RSS samples. Never invent a peak.
    warnings = []
    if not rss_peak:
        warnings.append("No measured RSS sample; increase duration")
    if load["generator_cpu_percent"] >= 85:
        warnings.append("Generator CPU >=85%; capacity may be generator-limited")
    if mode == "fixed" and load["admission_lag_ms"]["p99"] > 5:
        warnings.append("Fixed-rate p99 admission lag exceeds 5 ms; scheduled latency includes backlog")
    if data["warmup"]["count"] < 10000:
        warnings.append("Warm-up processed fewer than 10,000 messages; JIT steady state is uncertain")
    if language == "java" and args.allow_other_versions:
        warnings.append("Development runtime override: not the pinned JDK")
    if language == "python" and versions["python"]["version"] != CONFIG["python_version"]:
        warnings.append("Development runtime override: not the pinned CPython")
    gc = gc_metrics(language, handler_metrics, gc_log)
    metrics = {"throughput_mps": load["throughput_mps"],
               "handler_cpu_seconds": handler_metrics["process_cpu_ns"] / 1e9,
               "handler_cpu_percent": 100 * handler_metrics["process_cpu_ns"] / (load["elapsed_seconds"] * 1e9),
               "peak_rss_mib": rss_peak / 1024 if rss_peak else None,
               "lifetime_peak_rss_mib": lifetime_hwm / 1024,
               "generator_cpu_percent": load["generator_cpu_percent"],
               "generator_peak_rss_mib": generator_rss_peak / 1024 if generator_rss_peak else None,
               "gc_pause_count": gc["pause_count"], "gc_pause_total_ms": gc["pause_total_ms"],
               "gc_pause_max_ms": gc["pause_ms"]["max"], "gc_pause_p99_ms": gc["pause_ms"]["p99"],
               "gc_collections": gc["collections"], "allocation_stall_count": gc["allocation_stall_count"],
               "allocation_stall_total_ms": gc["allocation_stall_total_ms"],
               "retained": handler_metrics["retained"], "evicted": handler_metrics["evicted"]}
    metrics.update({"latency_" + name + "_ms": value for name, value in load["latency_ms"].items()})
    (directory / "resource-samples.json").write_text(json.dumps(samples))
    file_bytes = output_file.stat().st_size
    # Validate actual file contents, IDs, count and transform outside the measured interval.
    expected_first = 1_000_000_000_000_000 + data["warmup"]["count"]
    output_count = 0
    with output_file.open(encoding="utf-8") as stream:
        for line in stream:
            message = json.loads(line)
            if (message["id"] != expected_first + output_count or message["symbol"] != "EURUSD"
                    or message["notional"] != float(message["qty"]) * float(message["price"])
                    or type(message["processed_ts"]) is not int):
                raise RuntimeError("output content validation failed")
            output_count += 1
    if output_count != load["count"] or handler_metrics["count"] != output_count:
        raise RuntimeError("file/acknowledgement/handler counts differ")
    if args.delete_output:
        output_file.unlink()
    print(f"{name}: {metrics['throughput_mps']:,.0f} msg/s, p99 {metrics['latency_p99_ms']:.3f} ms", flush=True)
    return {"name": name, "language": language, "scenario": scenario, "mode": mode,
            "repeat": repeat, "execution_order": order, "metrics": metrics, "gc": gc,
            "count": load["count"], "max_os_threads": max_threads,
            "cgroup_memory_peak_mib": cgroup_peak, "output_bytes": file_bytes,
            "output_validated": True, "warnings": warnings, "command": command,
            "generator_command": loader_command, "data": data}


def environment(args, versions):
    cpuinfo = Path("/proc/cpuinfo").read_text()
    model = re.search(r"model name\s*:\s*(.*)", cpuinfo)
    def read(path):
        try: return Path(path).read_text().strip()
        except OSError: return None
    filesystem = subprocess.run(["stat", "-f", "-c", "%T", str(args.output)], capture_output=True, text=True, check=True).stdout.strip()
    commit = os.environ.get("GITHUB_SHA") or subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"os": platform.platform(), "cpu_model": model[1] if model else "unknown",
            "allowed_cpus": args.eligible_cpus, "handler_cpu": args.handler_cpu, "control_cpu": args.control_cpu,
            "generator_cpu": args.generator_cpu, "handler_cpu_topology": cpu_topology(args.handler_cpu),
            "generator_cpu_topology": cpu_topology(args.generator_cpu), "versions": versions,
            "filesystem": filesystem, "output_directory": str(args.output), "commit": commit,
            "container_cpu_quota": read("/sys/fs/cgroup/cpu.max"),
            "container_memory_max": read("/sys/fs/cgroup/memory.max"),
            "memory_control": "cgroup v2 memory.max, swap disabled" if args.cgroup_parent else "sampled RSS guard, not a hard heap limit",
            "github_repository": os.environ.get("GITHUB_REPOSITORY"), "github_run_id": os.environ.get("GITHUB_RUN_ID")}


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "results/latest" / CONFIG["id"])
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--java", default="java")
    parser.add_argument("--javac", default="javac")
    for flag, default in [("runs", "runs"), ("payload-bytes", "payload_bytes"), ("window", "window"),
                          ("flush-every", "flush_every"), ("buffer-bytes", "buffer_bytes"),
                          ("heap-mib", "heap_mib"), ("memory-limit-mib", "memory_limit_mib"),
                          ("retain", "retain"), ("allocation-rounds", "allocation_rounds")]:
        parser.add_argument("--" + flag, type=int, default=DEFAULTS[default])
    parser.add_argument("--warmup", type=float, default=DEFAULTS["warmup_seconds"])
    parser.add_argument("--duration", type=float, default=DEFAULTS["duration_seconds"])
    parser.add_argument("--rate", type=float, default=DEFAULTS["fixed_rate_mps"])
    parser.add_argument("--scenarios", nargs="+", choices=["A", "B", "C"], default=["A", "B", "C"])
    parser.add_argument("--modes", nargs="+", choices=["unlimited", "fixed"], default=["unlimited", "fixed"])
    parser.add_argument("--languages", nargs="+", choices=["python", "java"], default=["python", "java"])
    parser.add_argument("--handler-cpu", type=int)
    parser.add_argument("--generator-cpu", type=int)
    parser.add_argument("--control-cpu", type=int)
    parser.add_argument("--cgroup-parent", type=Path)
    parser.add_argument("--seed", type=int, default=20261012)
    parser.add_argument("--run-timeout", type=float, default=600)
    parser.add_argument("--allow-other-versions", action="store_true", help="development only, explicitly labeled")
    parser.add_argument("--smoke", action="store_true", help="correctness check, never publish as benchmark evidence")
    parser.add_argument("--messages", type=int, default=0)
    parser.add_argument("--delete-output", action="store_true", help="after full correctness validation")
    parser.add_argument("--save-latencies", action="store_true")
    args = parser.parse_args()
    if args.smoke:
        args.runs, args.warmup, args.duration, args.messages, args.retain = 1, .1, .2, 100, 32
    if args.runs < 5 and not args.smoke:
        parser.error("at least five measured runs are required; use --smoke for tests")
    if args.allow_other_versions and not args.smoke:
        parser.error("--allow-other-versions is allowed only with --smoke")
    for name in ("warmup", "duration", "payload_bytes", "window", "flush_every", "buffer_bytes",
                 "heap_mib", "memory_limit_mib", "retain", "allocation_rounds", "run_timeout"):
        if not math.isfinite(getattr(args, name)) or getattr(args, name) <= 0:
            parser.error(name + " must be finite and positive")
    if args.rate <= 0 or args.messages < 0: parser.error("rate must be positive; messages cannot be negative")
    if args.heap_mib < 64 or args.heap_mib >= args.memory_limit_mib:
        parser.error("heap >=64 MiB and heap < process memory budget are required")
    if sys.platform != "linux": parser.error("this harness requires Linux /proc and CPU affinity")
    args.eligible_cpus = sorted(os.sched_getaffinity(0))
    args.handler_cpu, args.generator_cpu = choose_cpus(args.handler_cpu, args.generator_cpu)
    if args.control_cpu is None:
        args.control_cpu = next((cpu for cpu in args.eligible_cpus
                                 if cpu_topology(cpu) not in (cpu_topology(args.handler_cpu), cpu_topology(args.generator_cpu))),
                                args.generator_cpu)
    if args.control_cpu not in args.eligible_cpus or cpu_topology(args.control_cpu) == cpu_topology(args.handler_cpu):
        parser.error("control CPU must be allowed and separate from the handler core")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "results.json").exists() or (args.output / "raw").exists():
        parser.error("output must be empty; root run_benchmarks replaces its latest output automatically")
    args.python = shutil.which(args.python) or str(Path(args.python).resolve())
    args.java = shutil.which(args.java) or str(Path(args.java).resolve())
    args.javac = shutil.which(args.javac) or str(Path(args.javac).resolve())
    if args.cgroup_parent: args.cgroup_parent = args.cgroup_parent.resolve()
    return args


def main():
    args = arguments()
    probe = "import json,platform,sys,sysconfig;print(json.dumps({'version':platform.python_version(),'implementation':sys.implementation.name,'gil_disabled':bool(sysconfig.get_config_var('Py_GIL_DISABLED')),'build':sys.version,'config_args':sysconfig.get_config_var('CONFIG_ARGS')}))"
    py = json.loads(subprocess.run([args.python, "-I", "-c", probe], text=True, capture_output=True, check=True).stdout)
    if py["implementation"] != "cpython" or py["gil_disabled"]:
        raise RuntimeError("default-GIL CPython is required")
    if not args.allow_other_versions and py["version"] != CONFIG["python_version"]:
        raise RuntimeError(f"need CPython {CONFIG['python_version']}, found {py['version']}")
    java = subprocess.run([args.java, "-version"], text=True, capture_output=True, check=True).stderr
    javac = subprocess.run([args.javac, "-version"], text=True, capture_output=True, check=True).stdout.strip()
    release = 17 if args.allow_other_versions else CONFIG["java_release"]
    build = args.output / "build"
    build.mkdir()
    subprocess.run([args.javac, "--release", str(release), "-d", str(build), str(HERE / "java/Handler.java")], check=True)
    versions = {"python": py, "java": java.strip(), "javac": javac}
    metadata = environment(args, versions)
    os.sched_setaffinity(0, {args.control_cpu})
    settings = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    runs = []
    randomizer = random.Random(args.seed)
    plan = []
    for repeat in range(1, args.runs + 1):
        cells = [(scenario, mode) for scenario in args.scenarios for mode in args.modes]
        randomizer.shuffle(cells)
        for scenario, mode in cells:
            languages = args.languages[:]
            randomizer.shuffle(languages)
            plan.extend((language, scenario, mode, repeat) for language in languages)
    try:
        for order, (language, scenario, mode, repeat) in enumerate(plan, 1):
            runs.append(run_one(args, language, scenario, mode, repeat, order, build, versions))
            partial = {"schema_version": 1, "counter_measure": CONFIG["id"], "title": CONFIG["title"],
                       "status": "running", "smoke": args.smoke, "environment": metadata, "settings": settings,
                       "runs": runs, "aggregates": aggregate(runs)}
            (args.output / "partial-results.json").write_text(json.dumps(partial, indent=2) + "\n")
    except Exception as error:
        failure = {"status": "failed", "error": str(error), "completed_runs": len(runs), "settings": settings}
        (args.output / "failure.json").write_text(json.dumps(failure, indent=2) + "\n")
        raise
    result = {"schema_version": 1, "counter_measure": CONFIG["id"], "title": CONFIG["title"],
              "status": "complete", "smoke": args.smoke,
              "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "environment": metadata, "settings": settings, "runs": runs, "aggregates": aggregate(runs)}
    (args.output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.output / "partial-results.json").unlink()


if __name__ == "__main__":
    main()
