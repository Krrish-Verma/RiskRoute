from __future__ import annotations

import argparse
import asyncio
import math
import statistics
import time

import httpx


PAYLOAD = {
    "origin": "Downtown Dallas, Dallas, TX",
    "destination": "North Dallas, Dallas, TX",
    "driver_profile": "normal_driver",
    "preferences": {"prefer_safest": True},
}


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


async def run_load_test(base_url: str, requests: int, concurrency: int) -> tuple[list[float], list[str]]:
    semaphore = asyncio.Semaphore(concurrency)
    durations: list[float] = []
    errors: list[str] = []

    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=30.0) as client:
        async def execute(index: int) -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.post("/api/v1/analyze-route", json=PAYLOAD)
                    duration_ms = (time.perf_counter() - started) * 1000
                    durations.append(duration_ms)
                    if response.status_code != 200:
                        errors.append(
                            f"request {index}: HTTP {response.status_code} "
                            f"request_id={response.headers.get('x-request-id', 'missing')}"
                        )
                except Exception as exc:
                    durations.append((time.perf_counter() - started) * 1000)
                    errors.append(f"request {index}: {exc.__class__.__name__}")

        await asyncio.gather(*(execute(index) for index in range(requests)))
    return durations, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded RiskRoute analyze-route load smoke test.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--maximum-p95-ms", type=float, default=5_000)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1 or args.concurrency > args.requests:
        raise SystemExit("requests must be positive and concurrency must be between 1 and requests")

    durations, errors = asyncio.run(
        run_load_test(args.base_url, args.requests, args.concurrency)
    )
    p50 = statistics.median(durations)
    p95 = _percentile(durations, 0.95)
    print(
        f"requests={len(durations)} errors={len(errors)} "
        f"p50_ms={p50:.1f} p95_ms={p95:.1f} max_ms={max(durations):.1f}"
    )
    for error in errors[:10]:
        print(error)
    if errors:
        raise SystemExit(1)
    if p95 > args.maximum_p95_ms:
        raise SystemExit(
            f"p95 {p95:.1f}ms exceeds configured limit {args.maximum_p95_ms:.1f}ms"
        )


if __name__ == "__main__":
    main()
