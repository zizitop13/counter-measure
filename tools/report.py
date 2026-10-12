#!/usr/bin/env python3
"""Render counter-measure schema v1 as standalone HTML and Markdown."""
import argparse
import html
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
QUANTILES = ("p50", "p90", "p99", "p99.9", "max")
STYLE = """+:root{color-scheme:light;--ink:#182523;--muted:#586964;--line:#dbe3df;--green:#11634c;--blue:#305caf}
*{box-sizing:border-box}body{margin:0;background:#f4f6f2;color:var(--ink);font:15px/1.55 system-ui,sans-serif}
main{max-width:1480px;margin:auto;padding:42px 30px 64px}a{color:var(--green)}h1{font-size:clamp(32px,4vw,54px);line-height:1.08;letter-spacing:-1.7px;max-width:920px;margin:14px 0 20px}h2{font-size:22px;margin:28px 0 12px}p{max-width:940px}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:2px;color:var(--green);font-weight:700}.muted{color:var(--muted)}.chips{display:flex;flex-wrap:wrap;gap:8px}.chip{background:white;border:1px solid var(--line);padding:5px 11px;border-radius:30px;font-size:12px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:16px;margin:24px 0}.card{background:white;border:1px solid var(--line);border-radius:14px;padding:22px}.card .big{font-size:30px;line-height:1.2;letter-spacing:-.6px;margin:12px 0 7px}.bar{height:9px;border-radius:5px;margin:9px 0;background:#e6ebe8;overflow:hidden}.bar span{display:block;height:100%;background:var(--green)}.bar.java span{background:var(--blue)}.alert{padding:13px 17px;background:#fff3d9;border:1px solid #edd7a4;border-radius:10px;margin:18px 0}.panel{background:white;border:1px solid var(--line);border-radius:14px;padding:20px;margin:20px 0}.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap}select{font:inherit;padding:7px 10px;border:1px solid var(--line);border-radius:6px;background:white}button{font:inherit;padding:7px 12px;background:white;border:1px solid var(--line);border-radius:6px;cursor:pointer}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:13px}th{font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);background:#f5f7f5}th,td{text-align:right;padding:12px 11px;border-bottom:1px solid var(--line);white-space:nowrap}th:first-child,td:first-child{text-align:left}td .range{display:block;color:var(--muted);font-size:10px}.python-label{color:var(--green);font-weight:600}.java-label{color:var(--blue);font-weight:600}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}details{margin:14px 0}summary{font-weight:600;cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.5;background:#f5f7f5;padding:14px;border-radius:8px}.notes li{margin:8px 0}footer{margin-top:34px;font-size:12px;color:var(--muted)}code{background:#eef2ee;padding:1px 4px;border-radius:3px}
"""


def esc(value):
    return html.escape(str(value), quote=True)


def number(value, digits=2):
    return "—" if value is None else f"{value:,.{digits}f}"


def cell(metric, digits=2):
    title = f"min {number(metric['min'], digits)}; max {number(metric['max'], digits)}; IQR {number(metric['iqr'], digits)}"
    return f'<td title="{esc(title)}">{number(metric["median"], digits)}<span class="range">{number(metric["min"], digits)}–{number(metric["max"], digits)}</span></td>'


def markdown(data):
    text = [f"# {data['title']}", "", f"Generated: {data['created_at']}; commit: `{data['environment']['commit']}`.", "",
            "Every cell is the median across runs [minimum–maximum]. Latencies and GC pauses are milliseconds.", "",
            "| Scenario | Mode | Runtime | Runs | msg/s | p50 | p90 | p99 | p99.9 | max | CPU % | CPU s | RSS MiB | GC pauses | GC total ms | GC p99 ms | GC max ms | GC cycles | Stall count | Stall total ms | Generator CPU % | Generator RSS MiB | Retained | Evicted |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    fields = ["throughput_mps"] + ["latency_" + q + "_ms" for q in QUANTILES]
    fields += ["handler_cpu_percent", "handler_cpu_seconds", "peak_rss_mib", "gc_pause_count", "gc_pause_total_ms",
               "gc_pause_p99_ms", "gc_pause_max_ms", "gc_collections", "allocation_stall_count",
               "allocation_stall_total_ms", "generator_cpu_percent", "generator_peak_rss_mib", "retained", "evicted"]
    for group in data["aggregates"]:
        values = []
        for field in fields:
            metric = group["metrics"][field]
            digits = 0 if field in ("throughput_mps", "gc_pause_count", "gc_collections", "allocation_stall_count", "retained", "evicted") else 3
            values.append(f"{number(metric['median'], digits)} [{number(metric['min'], digits)}–{number(metric['max'], digits)}]")
        text.append("| " + " | ".join([group["scenario"], group["mode"], group["language"], str(group["runs"])] + values) + " |")
    text.extend(["", "GC max/p99 is — when no pauses were observed; zero pause count does not mean zero reference-counting overhead.", "",
                 "## Environment", "", "```json", json.dumps(data["environment"], indent=2), "```", "",
                 "## Controls", "", "```json", json.dumps(data["settings"], indent=2), "```", ""])
    warnings = sorted({warning for run in data["runs"] for warning in run["warnings"]})
    if warnings:
        text.extend(["## Observations", ""] + ["- " + warning for warning in warnings] + [""])
    return "\n".join(text)


def generic_html(data):
    fields = sorted({field for group in data["aggregates"] for field in group["metrics"]})
    rows = []
    for group in data["aggregates"]:
        first = f'<td>{esc(group["language"])} · {esc(group["scenario"])} · {esc(group["mode"])}<span class="range">{group["runs"]} runs</span></td>'
        rows.append('<tr>' + first + ''.join(cell(group["metrics"].get(field, {"median":None,"min":None,"max":None,"iqr":None}), 3) for field in fields) + '</tr>')
    return f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(data["title"])}</title><style>{STYLE}</style><main><a href="../index.html">← All counter-measures</a><div class="eyebrow">{esc(data["counter_measure"])}</div><h1>{esc(data["title"])}</h1><p class="muted">Median across per-run measurements. Smaller text shows minimum–maximum; hover for IQR.</p><section class="panel table-wrap"><table><thead><tr><th>Runtime / scenario / mode</th>{"".join("<th>"+esc(field)+"</th>" for field in fields)}</tr></thead><tbody>{"".join(rows)}</tbody></table></section><section class="panel"><a href="results.json" download>Full results JSON</a> · <a href="summary.md" download>Markdown</a><details><summary>Environment and configuration</summary><pre>{esc(json.dumps({"environment":data["environment"],"settings":data["settings"]},indent=2))}</pre></details></section><footer>{esc(data["created_at"])}</footer></main></html>'


def comparison_html(data):
    if data["counter_measure"] != "001-single-thread-json":
        return generic_html(data)
    env, settings = data["environment"], data["settings"]
    warnings = sorted({warning for run in data["runs"] for warning in run["warnings"]})
    cards = []
    for scenario, title in (("A", "Short-lived objects"), ("B", "Allocation pressure"), ("C", "Retained cycles")):
        groups = {g["language"]: g for g in data["aggregates"] if g["scenario"] == scenario and g["mode"] == "unlimited"}
        if set(groups) != {"python", "java"}: continue
        py = groups["python"]["metrics"]["throughput_mps"]["median"]
        java = groups["java"]["metrics"]["throughput_mps"]["median"]
        winner, ratio = ("Java", java / py) if java >= py else ("Python", py / java)
        scale = max(py, java)
        cards.append(f'<article class="card"><div class="eyebrow">{scenario} · {title}</div><div class="big">{winner} {ratio:.2f}×</div><div class="muted">Measured throughput ratio</div><div class="bar python"><span style="width:{100*py/scale:.2f}%"></span></div><small>Python {number(py,0)} msg/s</small><div class="bar java"><span style="width:{100*java/scale:.2f}%"></span></div><small>Java {number(java,0)} msg/s</small></article>')
    fields = ["throughput_mps"] + ["latency_" + q + "_ms" for q in QUANTILES]
    fields += ["handler_cpu_percent", "peak_rss_mib", "gc_pause_total_ms", "gc_pause_max_ms", "generator_cpu_percent"]
    headers = ["Runtime / scenario", "msg/s", "p50 ms", "p90 ms", "p99 ms", "p99.9 ms", "max ms", "CPU %", "RSS MiB", "GC total ms", "GC max ms", "Load CPU %"]
    rows = []
    gc_rows = []
    for group in sorted(data["aggregates"], key=lambda g: (g["mode"], g["scenario"], g["language"])):
        language, metrics = group["language"], group["metrics"]
        label = "CPython" if language == "python" else "Java ZGC"
        attrs = f'data-mode="{esc(group["mode"])}" data-scenario="{esc(group["scenario"])}"'
        first = f'<td><span class="{language}-label">{label}</span> · {esc(group["scenario"])}<span class="range">{group["runs"]} runs</span></td>'
        values = "".join(cell(metrics[field], 0 if field == "throughput_mps" else 3) for field in fields)
        rows.append(f'<tr {attrs}>{first}{values}</tr>')
        gc_fields = ["gc_pause_count", "gc_pause_total_ms", "gc_pause_p99_ms", "gc_pause_max_ms", "gc_collections", "allocation_stall_count", "allocation_stall_total_ms", "retained", "evicted", "handler_cpu_seconds", "lifetime_peak_rss_mib", "generator_peak_rss_mib"]
        gc_rows.append(f'<tr {attrs}>{first}' + "".join(cell(metrics[field], 0 if field in ("gc_pause_count", "gc_collections", "allocation_stall_count", "retained", "evicted") else 3) for field in gc_fields) + '</tr>')
    alert = '<div class="alert">Correctness smoke test only. These numbers are not benchmark evidence.</div>' if data["smoke"] else ""
    if warnings:
        alert += '<div class="alert"><strong>Read with the measurements:</strong><ul>' + "".join('<li>' + esc(w) + '</li>' for w in warnings) + '</ul></div>'
    workflow = ""
    if env.get("github_run_id") and env.get("github_repository"):
        workflow = f'<a href="https://github.com/{esc(env["github_repository"])}/actions/runs/{esc(env["github_run_id"])}">Workflow and raw logs</a> · '
    py_version = env["versions"]["python"]["version"]
    chips = [f"CPython {py_version} · GIL", "JDK " + env["versions"]["java"].splitlines()[0],
             f"{settings['runs']} runs per cell", f"{settings['payload_bytes']} bytes/message",
             f"{settings['warmup']}s warm-up + {settings['duration']}s measurement",
             f"handler CPU {env['handler_cpu']} · loader CPU {env['generator_cpu']}"]
    gc_headers = ["Runtime / scenario", "Pause count", "Total ms", "p99 ms", "Max ms", "GC cycles", "Stall count", "Stall ms", "Retained", "Evicted", "CPU s", "Lifetime RSS MiB", "Load RSS MiB"]
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(data['title'])} — Counter-measure</title><style>{STYLE}</style><main>
<a href="../index.html">← All counter-measures</a><div class="eyebrow" style="margin-top:28px">Counter-measure 001 / measured evidence</div><h1>One thread.<br>Two runtimes.</h1><p class="muted">TCP → JSON parse → transform → buffered file append → acknowledgement. Compare capacity under unlimited load, then latency at the same offered rate. Ratios apply to this workload and machine.</p>
<div class="chips">{''.join('<span class="chip">'+esc(chip)+'</span>' for chip in chips)}</div>{alert}<div class="cards">{''.join(cards)}</div>
<section class="panel"><div class="controls"><h2 style="margin:0 auto 0 0">Measured results</h2><label>Load <select id="mode"><option value="unlimited">Unlimited / capacity</option><option value="fixed">Fixed / {settings['rate']:g} msg/s</option></select></label><label>Scenario <select id="scenario"><option value="all">All scenarios</option><option value="A">A · Short-lived</option><option value="B">B · Allocation</option><option value="C">C · Cycles</option></select></label></div><p class="muted">Median of per-run measurements; the smaller line shows minimum–maximum. Hover for IQR. Every latency sample is included; percentiles are not pooled across runs.</p><div class="table-wrap"><table><thead><tr>{''.join('<th>'+h+'</th>' for h in headers)}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
<section class="panel"><h2>GC, retained state, and resource detail</h2><p class="muted">CPython callbacks time cyclic collections. Reference counting is part of CPU and latency, but absent from GC pauses. ZGC pauses exclude concurrent work; allocation stalls are listed separately. “—” means no observed pause. RSS is sampled every 20 ms; lifetime HWM includes warm-up.</p><div class="table-wrap"><table><thead><tr>{''.join('<th>'+h+'</th>' for h in gc_headers)}</tr></thead><tbody>{''.join(gc_rows)}</tbody></table></div></section>
<div class="grid"><section class="panel"><h2>What completion means</h2><p>An acknowledgement follows parse, transform, serialization, and buffered append. Every {settings['flush_every']} messages, it also follows a flush to the OS. No fsync is requested. Throughput includes queue drain and the final flush.</p><p>Fixed-rate latency starts at scheduled arrival, including admission backlog. Unlimited latency starts when a message enters the loader’s bounded buffer (window {settings['window']}). Neither is a disk-durability measurement.</p><h2>Scenarios</h2><ul class="notes"><li><strong>A:</strong> short-lived message trees.</li><li><strong>B:</strong> {settings['allocation_rounds']} extra parse/serialize passes with temporary trees.</li><li><strong>C:</strong> grow a ring up to {settings['retain']:,} message graphs, each with a two-way reference cycle; evicted graphs become collectible.</li></ul></section>
<section class="panel"><h2>Controls and limits</h2><ul class="notes"><li>One application thread. JVM GC and compiler threads share the handler’s single-core affinity.</li><li>Fresh process per run, warm-up in the same process, paired randomized language order.</li><li>Both use {settings['buffer_bytes']:,}-byte file buffers and the {esc(env['filesystem'])} filesystem.</li><li>Java heap maximum: {settings['heap_mib']} MiB. Common process budget: {settings['memory_limit_mib']} MiB; {esc(env['memory_control'])}. CPython has no equivalent Xmx heap setting.</li><li>Python’s standard JSON module includes C code. Java uses the included generic JSON parser because the JDK provides no JSON parser. Functional equivalence is checked; bytes and object layouts can differ.</li><li>Hardware: {esc(env['cpu_model'])}. Shared CI and virtualization can add noise. Check the spread and generator CPU before drawing a conclusion.</li></ul></section></div>
<section class="panel"><h2>Reproduce and inspect</h2><p>{workflow}<a href="results.json" download>Full results JSON</a> · <a href="summary.md" download>Markdown results</a></p><details><summary>Environment, exact runtime builds, and configuration</summary><pre>{esc(json.dumps({'environment':env,'settings':settings},indent=2))}</pre></details><details><summary>Every run: metrics, message counts, and observations</summary><pre>{esc(json.dumps([{'name':r['name'],'count':r['count'],'metrics':r['metrics'],'warnings':r['warnings'],'command':r['command']} for r in data['runs']],indent=2))}</pre></details></section>
<footer>Latest successful result for this counter-measure · {esc(data['created_at'])} · source {esc(env['commit'])}. A new successful run replaces this page.</footer></main><script>
const mode=document.querySelector('#mode'),scenario=document.querySelector('#scenario');function filter(){{document.querySelectorAll('tr[data-mode]').forEach(row=>{{row.hidden=row.dataset.mode!==mode.value||(scenario.value!=='all'&&row.dataset.scenario!==scenario.value)}})}}mode.addEventListener('change',filter);scenario.addEventListener('change',filter);if(!document.querySelector('tr[data-mode="unlimited"]'))mode.value='fixed';filter();
</script></html>'''


def build_report(results_root, site, allow_smoke=False):
    catalog = json.loads((ROOT / "counter-measures/catalog.json").read_text())["counter_measures"]
    if site.exists():
        # Delete only this generated site's directory, never arbitrary parent paths.
        if not (site / ".counter-measure-site").exists():
            raise ValueError("refusing to replace a directory without the generated-site marker")
        shutil.rmtree(site)
    site.mkdir(parents=True)
    (site / ".counter-measure-site").write_text("generated\n")
    (site / ".nojekyll").touch()
    cards = []
    for entry in catalog:
        source = results_root / entry["id"] / "results.json"
        if not source.exists():
            cards.append(f'<article class="card"><div class="eyebrow">{esc(entry["id"])}</div><h2>{esc(entry["title"])}</h2><p class="muted">No successful measurement published yet.</p></article>')
            continue
        data = json.loads(source.read_text())
        if data["schema_version"] != 1 or data["status"] != "complete":
            raise ValueError("only complete schema-v1 results can be reported")
        if data["smoke"] and not allow_smoke:
            raise ValueError("smoke measurements cannot be published")
        if not data["smoke"] and any(g["runs"] < 5 for g in data["aggregates"]):
            raise ValueError("each published cell requires five measured runs")
        destination = site / entry["id"]
        destination.mkdir()
        shutil.copy2(source, destination / "results.json")
        summary = markdown(data)
        (destination / "summary.md").write_text(summary, encoding="utf-8")
        (source.parent / "summary.md").write_text(summary, encoding="utf-8")
        (destination / "index.html").write_text(comparison_html(data), encoding="utf-8")
        cards.append(f'<article class="card"><div class="eyebrow">{esc(entry["id"])}</div><h2>{esc(entry["title"])}</h2><p>{esc(" vs ".join(entry["languages"]))}</p><p class="muted">{esc(data["created_at"])} · {data["settings"]["runs"]} runs per cell</p><a href="{esc(entry["id"])}/index.html">Open measurements →</a></article>')
    index = f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Counter-measure</title><style>{STYLE}</style><main><div class="eyebrow">Counter-measure / performance experiments</div><h1>Measure the trade-off.</h1><p class="muted">Reproducible comparisons of languages, runtimes, and implementation choices. Each topic shows its latest successful measurements, the spread across repeated runs, and the controls behind the numbers.</p><div class="cards">{"".join(cards)}</div><footer>Source and reproduction instructions: <a href="https://github.com/zizitop13/counter-measure">zizitop13/counter-measure</a></footer></main></html>'
    (site / "index.html").write_text(index, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=ROOT / "results/latest")
    parser.add_argument("--site", type=Path, default=ROOT / "results/latest/site")
    parser.add_argument("--allow-smoke", action="store_true")
    args = parser.parse_args()
    build_report(args.results_root.resolve(), args.site.resolve(), args.allow_smoke)
