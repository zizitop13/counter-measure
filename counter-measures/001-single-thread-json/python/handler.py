#!/usr/bin/env python3
"""One application thread; blocking TCP; compact UTF-8 NDJSON output."""

import argparse
import collections
import gc
import json
import math
import platform
import socket
import sys
import sysconfig
import time

MAX_INTEGER = (1 << 53) - 1


def validate_tree(value, depth=0):
    if depth > 64:
        raise ValueError("JSON nesting exceeds 64")
    if isinstance(value, dict):
        for key, child in value.items():
            key.encode("utf-8", "strict")
            validate_tree(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            validate_tree(child, depth + 1)
    elif isinstance(value, str):
        value.encode("utf-8", "strict")
    elif type(value) is int and abs(value) > MAX_INTEGER:
        raise ValueError("integer outside common exact range")
    elif type(value) is float and not math.isfinite(value):
        raise ValueError("non-finite JSON number")


def parse_message(line):
    value = json.loads(line.decode("utf-8", "strict") if isinstance(line, bytes) else line)
    validate_tree(value)
    if not isinstance(value, dict):
        raise ValueError("top-level JSON must be an object")
    return value


def transform(message):
    if type(message.get("id")) is not int or message["id"] < 0:
        raise ValueError("id must be a nonnegative integer")
    if type(message.get("qty")) is not int:
        raise ValueError("qty must be an integer")
    if type(message.get("price")) not in (int, float):
        raise ValueError("price must be a number")
    symbol = message.get("symbol")
    if not isinstance(symbol, str) or not symbol.isascii():
        raise ValueError("symbol must be an ASCII string")
    notional = float(message["qty"]) * float(message["price"])
    if not math.isfinite(notional):
        raise ValueError("notional overflow")
    message["processed_ts"] = time.time_ns() // 1_000_000
    message["notional"] = notional
    message["symbol"] = symbol.upper()
    return message


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8") + b"\n"


class Handler:
    def __init__(self, args):
        self.args = args
        self.writer = open(args.output, "ab", buffering=args.buffer_bytes)
        self.retained = collections.deque()
        self.count = self.total_count = self.evicted = 0
        self.blackhole = None
        self.gc_events = []
        self.gc_starts = {}
        self.measuring = False
        self.started_ns = self.cpu_started_ns = 0
        self.gc_before = gc.get_stats()
        self.final = None
        gc.callbacks.append(self.on_gc)

    def on_gc(self, phase, info):
        if not self.measuring:
            return
        generation = info["generation"]
        if phase == "start":
            self.gc_starts[generation] = time.perf_counter_ns()
        else:
            start = self.gc_starts.pop(generation, None)
            if start is not None:
                finish = time.perf_counter_ns()
                self.gc_events.append({"generation": generation,
                                       "pause_ms": (finish - start) / 1e6,
                                       "collected": info.get("collected", 0),
                                       "uncollectable": info.get("uncollectable", 0)})

    def begin(self):
        if self.measuring:
            raise ValueError("measurement already started")
        self.writer.close()
        # Warm-up output and live state are discarded, while the process stays alive.
        self.writer = open(self.args.output, "wb", buffering=self.args.buffer_bytes)
        self.retained.clear()
        gc.collect()  # Outside the measured interval, also done in Java.
        self.count = self.evicted = 0
        self.gc_events.clear()
        self.gc_starts.clear()
        self.gc_before = gc.get_stats()
        self.cpu_started_ns = time.process_time_ns()
        self.started_ns = time.perf_counter_ns()
        self.measuring = True
        return {"control": "begin", "started_ns": self.started_ns}

    def handle(self, line, message):
        transform(message)
        if self.args.scenario == "B":
            scratch = []
            for _ in range(self.args.allocation_rounds):
                copy = parse_message(line)
                scratch.append((copy, encode(copy)))
            self.blackhole = scratch
            self.blackhole = None
        elif self.args.scenario == "C":
            node = {"message": message}
            peer = {"owner": node}
            node["peer"] = peer
            self.retained.append(node)
            if len(self.retained) > self.args.retain:
                self.retained.popleft()
                self.evicted += 1
        self.writer.write(encode(message))
        self.count += 1
        self.total_count += 1
        if self.count % self.args.flush_every == 0:
            self.writer.flush()
        return str(message["id"]).encode("ascii") + b"\n"

    def finish(self):
        if self.final is not None:
            return self.final
        self.writer.flush()
        ended_ns = time.perf_counter_ns()
        cpu_ended_ns = time.process_time_ns()
        self.measuring = False
        self.writer.close()
        after = gc.get_stats()
        delta = [{k: stats[k] - before.get(k, 0)
                  for k in ("collections", "collected", "uncollectable")}
                 for before, stats in zip(self.gc_before, after)]
        self.final = {"control": "stop", "count": self.count,
                      "total_count_including_warmup": self.total_count,
                      "retained": len(self.retained), "evicted": self.evicted,
                      "elapsed_ns": ended_ns - self.started_ns if self.started_ns else None,
                      "process_cpu_ns": cpu_ended_ns - self.cpu_started_ns if self.started_ns else None,
                      "gc_events": self.gc_events, "gc_stats_before": self.gc_before,
                      "gc_stats_after": after, "gc_stats_delta": delta,
                      "python_version": platform.python_version(),
                      "gil_build": not bool(sysconfig.get_config_var("Py_GIL_DISABLED"))}
        return self.final


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--output", required=True)
    parser.add_argument("--flush-every", type=int, default=256)
    parser.add_argument("--buffer-bytes", type=int, default=65536)
    parser.add_argument("--max-message-bytes", type=int, default=1048576)
    parser.add_argument("--scenario", choices=["A", "B", "C"], default="A")
    parser.add_argument("--allocation-rounds", type=int, default=8)
    parser.add_argument("--retain", type=int, default=1000000)
    args = parser.parse_args()
    if min(args.flush_every, args.buffer_bytes, args.max_message_bytes,
           args.allocation_rounds, args.retain) < 1:
        parser.error("sizes and counts must be positive")
    if sys.implementation.name != "cpython" or sysconfig.get_config_var("Py_GIL_DISABLED"):
        parser.error("use default-GIL CPython, not a free-threaded build")
    return args


def main():
    args = arguments()
    handler = Handler(args)
    stopping = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((args.host, args.port))
            server.listen(16)
            print(json.dumps({"ready": True, "port": server.getsockname()[1],
                              "application_threads": 1}), flush=True)
            while not stopping:
                conn, _ = server.accept()
                with conn:
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    with conn.makefile("rb", buffering=args.buffer_bytes) as reader:
                        while line := reader.readline(args.max_message_bytes + 2):
                            if not line.endswith(b"\n") or len(line) - 1 > args.max_message_bytes:
                                raise ValueError("oversized or unterminated message")
                            line = line.decode("utf-8", "strict")
                            message = parse_message(line)
                            if "_control" in message:
                                if message["_control"] == "begin":
                                    reply = handler.begin()
                                elif message["_control"] == "stop":
                                    reply = handler.finish()
                                    stopping = True
                                else:
                                    raise ValueError("unknown control")
                                conn.sendall(encode(reply))
                            else:
                                conn.sendall(handler.handle(line, message))
                            if stopping:
                                break
    finally:
        final = handler.finish()
        gc.callbacks.remove(handler.on_gc)
        print(json.dumps(final, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
