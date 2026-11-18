"""Measure a supplied ONNX vision model on prepared, real model inputs."""

import argparse
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import onnxruntime as ort


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("inputs", type=Path, help="NPZ with one array per ONNX input name")
    parser.add_argument("--provider", default="CPUExecutionProvider")
    parser.add_argument("--iterations", type=int, default=100, choices=range(1, 1001))
    args = parser.parse_args()
    if args.provider not in ort.get_available_providers():
        parser.error(f"Execution provider is unavailable: {args.provider}")
    session = ort.InferenceSession(str(args.model), providers=[args.provider])
    if session.get_providers()[0] != args.provider:
        raise RuntimeError("ONNX Runtime fell back to a different execution provider")
    with np.load(args.inputs, allow_pickle=False) as records:
        batch = {item.name: records[item.name] for item in session.get_inputs()}
    for _ in range(10):
        session.run(None, batch)
    times = []
    for _ in range(args.iterations):
        start = perf_counter()
        session.run(None, batch)
        times.append((perf_counter() - start) * 1000)
    # Report batch latency and runs/s without assuming an image batch dimension.
    print(
        json.dumps(
            {
                "provider": args.provider,
                "iterations": args.iterations,
                "p50_ms": float(np.percentile(times, 50)),
                "p95_ms": float(np.percentile(times, 95)),
                "runs_per_second": 1000 / float(np.mean(times)),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
