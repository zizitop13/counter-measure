#!/usr/bin/env python3
"""Shared, separate-process, pipelined load generator using only the stdlib."""

import argparse
from array import array
from collections import deque
import json
import math
import os
from pathlib import Path
import selectors
import socket
import time

FIRST_ID = 1_000_000_000_000_000


def percentiles(samples, scale=1e6):
    values = sorted(samples)
    if not values:
        return {key: None for key in ("p50", "p90", "p99", "p99.9", "max")}
    result = {name: values[max(0, math.ceil(len(values) * q) - 1)] / scale
              for name, q in (("p50", .5), ("p90", .9), ("p99", .99), ("p99.9", .999))}
    result["max"] = values[-1] / scale
    return result


def payload_template(size, scenario):
    message = {"id": FIRST_ID, "symbol": "eurusd", "qty": 1000,
               "price": 1.0834, "ts": 1700000000000, "pad": ""}
    if scenario == "B":
        message["meta"] = [[1, 2.0, "level", True, None] for _ in range(4)]
    payload = json.dumps(message, separators=(",", ":")).encode() + b"\n"
    if len(payload) > size:
        raise ValueError(f"payload size must be at least {len(payload)} bytes for scenario {scenario}")
    message["pad"] = "x" * (size - len(payload))
    payload = json.dumps(message, separators=(",", ":")).encode() + b"\n"
    assert len(payload) == size
    prefix = b'{"id":'
    suffix = payload[len(prefix) + len(str(FIRST_ID)):]
    return prefix, suffix


def control(connection, command):
    connection.setblocking(True)
    connection.settimeout(120)
    connection.sendall(json.dumps({"_control": command}).encode() + b"\n")
    reply = bytearray()
    while not reply.endswith(b"\n"):
        chunk = connection.recv(65536)
        if not chunk:
            raise RuntimeError("handler disconnected during control")
        reply.extend(chunk)
    result = json.loads(reply)
    if result.get("control") != command:
        raise RuntimeError(f"unexpected control reply: {result}")
    connection.settimeout(None)
    return result


def phase(connection, seconds, rate, window, template, first_id, message_limit=0, collect_latencies=True):
    """Fixed-rate latency starts at the scheduled arrival, including admission lag.

    In unlimited mode it starts on admission to the bounded send buffer. Every
    scheduled fixed-rate message is sent, even if draining exceeds `seconds`.
    """
    prefix, suffix = template
    scheduled = math.ceil(seconds * rate) if rate else None
    if message_limit:
        scheduled = min(scheduled, message_limit) if scheduled else message_limit
    connection.setblocking(False)
    pending = deque()
    outgoing = bytearray()
    incoming = bytearray()
    latencies, wire_latencies, admission_lags = array("Q"), array("Q"), array("Q")
    sent = received = max_inflight = backpressure_events = 0
    per_second = []
    selector = selectors.DefaultSelector()
    selector.register(connection, selectors.EVENT_READ)
    cpu_start = time.process_time_ns()
    start = time.perf_counter_ns()
    deadline = start + int(seconds * 1e9)
    last_progress = start
    try:
        while True:
            now = time.perf_counter_ns()
            can_admit = sent < scheduled if scheduled is not None else now < deadline
            if not can_admit and not pending and not outgoing:
                break
            if now - last_progress > 120_000_000_000:
                raise TimeoutError("no acknowledgements for 120 seconds")
            added = 0
            while can_admit and len(pending) < window and added < 64:
                now = time.perf_counter_ns()
                intended = start + int(sent * 1e9 / rate) if rate else now
                if rate and intended > now:
                    break
                identity = first_id + sent
                outgoing.extend(prefix + str(identity).encode("ascii") + suffix)
                pending.append((identity, intended, now))
                if collect_latencies:
                    admission_lags.append(max(0, now - intended))
                sent += 1
                added += 1
                max_inflight = max(max_inflight, len(pending))
                can_admit = sent < scheduled if scheduled is not None else now < deadline
            if can_admit and len(pending) >= window:
                backpressure_events += 1
            if outgoing:
                try:
                    written = connection.send(outgoing)
                    del outgoing[:written]
                except BlockingIOError:
                    pass
            events = selectors.EVENT_READ | (selectors.EVENT_WRITE if outgoing else 0)
            selector.modify(connection, events)
            timeout = .02
            if can_admit and len(pending) < window:
                if rate:
                    due = start + int(sent * 1e9 / rate)
                    timeout = max(0., min(timeout, (due - time.perf_counter_ns()) / 1e9))
                else:
                    timeout = 0.
            for _, ready in selector.select(timeout):
                if ready & selectors.EVENT_READ:
                    chunk = connection.recv(65536)
                    if not chunk:
                        raise RuntimeError("handler disconnected before acknowledging all messages")
                    incoming.extend(chunk)
                    offset = 0
                    while True:
                        end = incoming.find(b"\n", offset)
                        if end < 0:
                            break
                        ack = int(incoming[offset:end])
                        expected, intended, admitted = pending.popleft()
                        if ack != expected:
                            raise RuntimeError(f"acknowledgement {ack} != {expected}")
                        finish = time.perf_counter_ns()
                        if collect_latencies:
                            latencies.append(finish - intended)
                            wire_latencies.append(finish - admitted)
                        second = int((finish - start) / 1e9)
                        while len(per_second) <= second:
                            per_second.append(0)
                        per_second[second] += 1
                        received += 1
                        last_progress = finish
                        offset = end + 1
                    if offset:
                        del incoming[:offset]
        finish = time.perf_counter_ns()
        cpu_finish = time.process_time_ns()
    finally:
        selector.close()
    if received == 0 or received != sent:
        raise RuntimeError("empty or incomplete measurement")
    return {"count": received, "sent": sent, "start_ns": start, "last_ack_ns": finish,
            "elapsed_seconds": (finish - start) / 1e9,
            "generator_cpu_seconds": (cpu_finish - cpu_start) / 1e9,
            "max_inflight": max_inflight, "backpressure_events": backpressure_events,
            "per_second_completions": per_second,
            "_latencies": latencies, "_wire_latencies": wire_latencies,
            "_admission_lags": admission_lags}


def summarize(result):
    result["latency_ms"] = percentiles(result.pop("_latencies"))
    result["wire_latency_ms"] = percentiles(result.pop("_wire_latencies"))
    result["admission_lag_ms"] = percentiles(result.pop("_admission_lags"))
    result["throughput_mps"] = result["count"] / result["elapsed_seconds"]
    result["generator_cpu_percent"] = 100 * result["generator_cpu_seconds"] / result["elapsed_seconds"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--duration", type=float, default=10)
    parser.add_argument("--warmup", type=float, default=10)
    parser.add_argument("--rate", type=float, default=0, help="messages/sec; zero = unlimited")
    parser.add_argument("--payload-bytes", type=int, default=1024, help="includes trailing LF")
    parser.add_argument("--window", type=int, default=1024)
    parser.add_argument("--scenario", choices=["A", "B", "C"], default="A")
    parser.add_argument("--messages", type=int, default=0, help="optional phase count limit for tests")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--save-latencies", action="store_true")
    args = parser.parse_args()
    if args.duration <= 0 or args.warmup <= 0 or args.rate < 0 or args.window < 1 or args.messages < 0:
        parser.error("durations/window must be positive; rate/messages cannot be negative")
    template = payload_template(args.payload_bytes, args.scenario)
    with socket.create_connection((args.host, args.port), timeout=30) as connection:
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        warmup = phase(connection, args.warmup, 0, args.window, template, FIRST_ID, args.messages,
                       collect_latencies=False)
        # Send BEGIN before calculating percentiles: warmed code is still hot.
        control(connection, "begin")
        print(json.dumps({"phase": "measurement", "pid": os.getpid()}), flush=True)
        measured = phase(connection, args.duration, args.rate, args.window, template,
                         FIRST_ID + warmup["count"], args.messages)
        handler_metrics = control(connection, "stop")
        measured["elapsed_seconds"] = (time.perf_counter_ns() - measured["start_ns"]) / 1e9
        print(json.dumps({"phase": "finished"}), flush=True)
    if handler_metrics["count"] != measured["count"]:
        raise RuntimeError("handler count differs from acknowledged count")
    if args.save_latencies:
        latency_path = args.output.with_suffix(".latencies-ns.u64")
        with latency_path.open("wb") as stream:
            measured["_latencies"].tofile(stream)
    report = {"warmup": summarize(warmup), "load": summarize(measured), "handler": handler_metrics,
              "payload_bytes": args.payload_bytes, "offered_rate_mps": args.rate,
              "offered_duration_seconds": args.duration, "window": args.window,
              "latency_unit": "ms", "percentile_method": "nearest rank; every acknowledged message",
              "raw_latency_byte_order": "native uint64" if args.save_latencies else None}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
