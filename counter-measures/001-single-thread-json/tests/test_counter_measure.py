"""Cross-language protocol and harness correctness tests; no third-party runner."""
import importlib.util
import json
import os
from pathlib import Path
import random
import selectors
import socket
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


runner = module("benchmark_runner", HERE / "run_benchmarks.py")
generator = module("load_generator", HERE / "load_generator.py")
reporter = module("reporter", ROOT / "tools/report.py")


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_dir = tempfile.TemporaryDirectory()
        cls.java = os.environ.get("JAVA", "java")
        subprocess.run([os.environ.get("JAVAC", "javac"), "--release", "27", "-d", cls.build_dir.name,
                        str(HERE / "java/Handler.java")], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build_dir.cleanup()

    def start(self, language, scenario="A", retain=32):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        output = Path(directory.name) / "output.ndjson"
        if language == "python":
            command = [sys.executable, "-I", str(HERE / "python/handler.py")]
        else:
            command = [self.java, "-XX:+UseZGC", "-Xms64m", "-Xmx512m", "-XX:ActiveProcessorCount=1",
                       "-XX:ConcGCThreads=1", "-XX:ParallelGCThreads=1", "-cp", self.build_dir.name, "Handler"]
        command += ["--port", "0", "--output", str(output), "--scenario", scenario,
                    "--flush-every", "7", "--buffer-bytes", "4096", "--retain", str(retain),
                    "--max-message-bytes", "4096"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=20)
        self.addCleanup(cleanup)
        ready = runner.read_ready(process)
        self.assertEqual(ready["application_threads"], 1)
        connection = socket.create_connection(("127.0.0.1", ready["port"]), timeout=20)
        connection.settimeout(20)
        self.addCleanup(connection.close)
        return process, connection, output, ready["port"]

    def send(self, connection, messages):
        connection.sendall(b"".join(json.dumps(m, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
                                    for m in messages))
        reader = connection.makefile("rb")
        self.addCleanup(reader.close)
        for message in messages:
            self.assertEqual(int(reader.readline()), message["id"])

    def stop(self, process, connection):
        metrics = generator.control(connection, "stop")
        stdout, stderr = process.communicate(timeout=20)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertEqual(json.loads(stdout), metrics)
        return metrics

    def test_nested_unicode_numbers_and_pipeline_equivalence(self):
        randomizer = random.Random(42)
        messages = [{"id": i, "symbol": "eurusd", "qty": randomizer.randrange(-20000, 20000),
                     "price": randomizer.choice([1.0834, -0.0, 1e-100, 2e100, 5]),
                     "ts": 1700000000000,
                     "extra": {"text": "München 👋\n\t\\\"", "items": [None, True, False, {"a": []}]}}
                    for i in range(100)]
        outputs = []
        for language in ("python", "java"):
            with self.subTest(language=language):
                process, connection, output, _ = self.start(language)
                generator.control(connection, "begin")
                self.send(connection, messages)
                metrics = self.stop(process, connection)
                self.assertEqual(metrics["count"], len(messages))
                rows = [json.loads(line) for line in output.read_text().splitlines()]
                for row, original in zip(rows, messages):
                    self.assertEqual(row["symbol"], "EURUSD")
                    self.assertEqual(row["notional"], float(original["qty"]) * float(original["price"]))
                    self.assertGreater(row.pop("processed_ts"), 1700000000000)
                outputs.append(rows)
        self.assertEqual(outputs[0], outputs[1])

    def test_warmup_discard_allocation_and_cycles(self):
        for language in ("python", "java"):
            for scenario in ("A", "B", "C"):
                with self.subTest(language=language, scenario=scenario):
                    process, connection, output, _ = self.start(language, scenario)
                    self.send(connection, [{"id": 1, "symbol": "eurusd", "qty": 1000, "price": 1.0834}])
                    generator.control(connection, "begin")
                    self.send(connection, [{"id": i, "symbol": "eurusd", "qty": 1000, "price": 1.0834}
                                           for i in range(2, 102)])
                    metrics = self.stop(process, connection)
                    self.assertEqual(metrics["count"], 100)
                    self.assertEqual(metrics["total_count_including_warmup"], 101)
                    self.assertEqual(len(output.read_text().splitlines()), 100)
                    self.assertEqual(json.loads(output.read_text().splitlines()[0])["id"], 2)
                    self.assertEqual(metrics["retained"], 32 if scenario == "C" else 0)
                    self.assertEqual(metrics["evicted"], 68 if scenario == "C" else 0)
                    self.assertGreater(metrics["process_cpu_ns"], 0)

    def test_sequential_connections_append_and_shutdown_count(self):
        for language in ("python", "java"):
            with self.subTest(language=language):
                process, connection, output, port = self.start(language)
                # No BEGIN: direct handler use keeps append semantics.
                connection.sendall(b'{"id":1,"symbol":"abc","qty":2,"price":3}\n')
                self.assertEqual(connection.recv(128), b"1\n")
                connection.close()
                second = socket.create_connection(("127.0.0.1", port), timeout=20)
                self.addCleanup(second.close)
                self.send(second, [{"id": 2, "symbol": "def", "qty": 2, "price": 3}])
                metrics = self.stop(process, second)
                self.assertEqual(metrics["count"], 2)
                self.assertEqual([json.loads(line)["id"] for line in output.read_text().splitlines()], [1, 2])

    def test_invalid_input_is_rejected_in_both_languages(self):
        bad_inputs = [b'{"id":1,"symbol":"x","qty":true,"price":1}\n',
                      b'{"id":1,"symbol":"x","qty":1.0,"price":1}\n',
                      b'{"id":1,"symbol":"x","qty":1,"price":NaN}\n',
                      b'{"id":1,"symbol":"x","qty":1,"price":1e309}\n',
                      b'{"id":1,"symbol":"x","qty":9007199254740992,"price":1}\n',
                      b'{"id":01,"symbol":"x","qty":1,"price":1}\n',
                      b'{"id":1,"symbol":"x","qty":1,"price":1,"extra":"\\ud800"}\n',
                      b'{"id":1,"symbol":"x","qty":1,"price":1,"extra":"\xff"}\n',
                      b'[]\n', b'{"id":1,}\n', b'x' * 4097 + b'\n']
        for language in ("python", "java"):
            for bad in bad_inputs:
                with self.subTest(language=language, input=bad[:80]):
                    process, connection, _, _ = self.start(language)
                    connection.sendall(bad)
                    _, stderr = process.communicate(timeout=20)
                    self.assertNotEqual(process.returncode, 0, stderr)

    def test_actual_generator_fixed_rate_and_complete_file(self):
        for language in ("python", "java"):
            with self.subTest(language=language):
                process, connection, output, port = self.start(language)
                connection.close()
                metrics_path = output.with_suffix(".json")
                generated = subprocess.run([sys.executable, "-I", str(HERE / "load_generator.py"),
                                           "--port", str(port), "--warmup", ".02", "--duration", ".05",
                                           "--rate", "2000", "--window", "8", "--payload-bytes", "256",
                                           "--output", str(metrics_path)], capture_output=True, text=True, timeout=30)
                self.assertEqual(generated.returncode, 0, generated.stderr)
                _, stderr = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, stderr)
                data = json.loads(metrics_path.read_text())
                self.assertEqual(data["load"]["count"], 100)
                self.assertEqual(data["handler"]["count"], 100)
                self.assertEqual(len(output.read_text().splitlines()), 100)
                self.assertLessEqual(data["load"]["max_inflight"], 8)
                self.assertGreater(data["load"]["latency_ms"]["p99"], 0)


class MetricsTests(unittest.TestCase):
    def test_payload_exact_bytes_and_percentile_definition(self):
        for scenario in ("A", "B", "C"):
            prefix, suffix = generator.payload_template(256, scenario)
            self.assertEqual(len(prefix + str(generator.FIRST_ID).encode() + suffix), 256)
        self.assertEqual(generator.percentiles([1, 2, 3, 4, 100], scale=1)["p99"], 100)
        self.assertIsNone(generator.percentiles([])["max"])

    def test_gc_logs_do_not_count_concurrent_cycles_as_pauses(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "gc.log"
            log.write_text("[0.100s][info][gc,phases] GC(0) Pause Mark Start 0.010ms\n"
                           "[1.100s][info][gc,phases] GC(1) Pause Mark Start 0.020ms\n"
                           "[1.120s][info][gc,phases] GC(1) Concurrent Mark 15.000ms\n"
                           "[1.130s][info][gc,phases] GC(1) Pause Mark End 0.030ms\n"
                           "[1.140s][info][gc] Allocation Stall (main) 4.000ms\n"
                           "[5.100s][info][gc,phases] GC(2) Pause Mark Start 0.100ms\n")
            handler = {"gc_window_start_uptime_ms": 1000, "gc_window_end_uptime_ms": 2000,
                       "gc_stats_before": {"ZGC Cycles": {"collections": 1}},
                       "gc_stats_after": {"ZGC Cycles": {"collections": 2}}}
            data = runner.gc_metrics("java", handler, log)
            self.assertEqual(data["pause_count"], 2)
            self.assertAlmostEqual(data["pause_total_ms"], .05)
            self.assertEqual(data["collections"], 1)
            self.assertEqual(data["allocation_stall_count"], 1)
            self.assertEqual(data["allocation_stall_total_ms"], 4)

    def test_median_spread_and_html_escaping(self):
        self.assertEqual(runner.spread([1, 2, 3, 4, 5]), {"median": 3, "min": 1, "max": 5, "iqr": 2})
        self.assertEqual(reporter.esc('<script>alert("x")</script>'), '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;')

    def test_future_counter_measure_has_generic_labels(self):
        data = {"counter_measure": "002-example", "title": "Example comparison", "created_at": "test",
                "environment": {}, "settings": {}, "aggregates": [
                    {"language": "rust", "scenario": "sample", "mode": "unlimited", "runs": 5,
                     "metrics": {"throughput_mps": runner.spread([1, 2, 3, 4, 5])}}]}
        page = reporter.comparison_html(data)
        self.assertIn("rust", page)
        self.assertNotIn("Java ZGC", page)
        self.assertNotIn("TCP", page)


if __name__ == "__main__":
    unittest.main()
