import argparse
import statistics
import time

import requests

ORDER_URL = "http://localhost:8000/order"
ORDER_CONFIG_URL = "http://localhost:8000/config"
INVENTORY_CONFIG_URL = "http://localhost:8001/config"
RESET_URL = "http://localhost:8001/reset"


def _post(url: str, payload: dict) -> requests.Response:
    return requests.post(url, json=payload, timeout=5)


def baseline_test(count: int) -> None:
    # No injected delay/failure for baseline.
    _post(RESET_URL, {})
    _post(INVENTORY_CONFIG_URL, {"delay_ms": 0, "fail_mode": "none"})
    _post(ORDER_CONFIG_URL, {"inventory_timeout_s": 3.0})
    latencies = []
    for i in range(count):
        payload = {"item_id": "burger", "qty": 1, "user_id": f"u{i}"}
        started = time.time()
        resp = _post(ORDER_URL, payload)
        elapsed = int((time.time() - started) * 1000)
        if resp.status_code != 200:
            print("baseline failure", resp.status_code, resp.text)
        latencies.append(elapsed)
    _print_stats("baseline", latencies)


def delay_test(count: int) -> None:
    # Force a 2s delay at inventory to measure tail latency impact.
    _post(RESET_URL, {})
    _post(INVENTORY_CONFIG_URL, {"delay_ms": 2000, "fail_mode": "none"})
    _post(ORDER_CONFIG_URL, {"inventory_timeout_s": 5.0})
    latencies = []
    for i in range(count):
        payload = {"item_id": "burrito", "qty": 1, "user_id": f"d{i}"}
        started = time.time()
        resp = _post(ORDER_URL, payload)
        elapsed = int((time.time() - started) * 1000)
        if resp.status_code != 200:
            print("delay failure", resp.status_code, resp.text)
        latencies.append(elapsed)
    _print_stats("delay_2s", latencies)


def failure_test(count: int) -> None:
    # Force timeouts to validate order service error handling.
    _post(RESET_URL, {})
    _post(INVENTORY_CONFIG_URL, {"delay_ms": 0, "fail_mode": "timeout"})
    _post(ORDER_CONFIG_URL, {"inventory_timeout_s": 1.0})
    failures = 0
    for i in range(count):
        payload = {"item_id": "salad", "qty": 1, "user_id": f"f{i}"}
        resp = _post(ORDER_URL, payload)
        if resp.status_code != 504:
            print("expected timeout", resp.status_code, resp.text)
        else:
            failures += 1
    print(f"timeout responses: {failures}/{count}")


def _print_stats(label: str, latencies: list[int]) -> None:
    p50 = int(statistics.median(latencies))
    p95 = int(statistics.quantiles(latencies, n=20)[18]) if len(latencies) >= 20 else max(latencies)
    avg = int(statistics.mean(latencies))
    print(f"{label} avg={avg}ms p50={p50}ms p95={p95}ms")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=int, default=0)
    parser.add_argument("--delay", type=int, default=0)
    parser.add_argument("--failure", type=int, default=0)
    args = parser.parse_args()

    if args.baseline:
        baseline_test(args.baseline)
    if args.delay:
        delay_test(args.delay)
    if args.failure:
        failure_test(args.failure)


if __name__ == "__main__":
    main()
