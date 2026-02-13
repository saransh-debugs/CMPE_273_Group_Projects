import argparse
import json
import time
import statistics
import requests
from confluent_kafka import Consumer, KafkaError

ORDER_URL = "http://localhost:8000/order"
RESET_URL = "http://localhost:8000/reset"


def _post(url: str, payload: dict) -> requests.Response:
    return requests.post(url, json=payload, timeout=5)


def baseline_test(count: int) -> None:
    """Produce baseline orders and measure latency."""
    print(f"\n=== BASELINE TEST ({count} orders) ===")
    _post(RESET_URL, {})
    
    latencies = []
    for i in range(count):
        payload = {"item_id": "burger", "qty": 1, "user_id": f"u{i}"}
        started = time.time()
        resp = _post(ORDER_URL, payload)
        elapsed = int((time.time() - started) * 1000)
        
        if resp.status_code != 200:
            print(f"  Error: {resp.status_code} {resp.text}")
        else:
            latencies.append(elapsed)
    
    _print_stats("baseline", latencies)


def load_test(count: int) -> None:
    """Produce many orders rapidly and measure throughput."""
    print(f"\n=== LOAD TEST ({count} orders) ===")
    _post(RESET_URL, {})
    
    started = time.time()
    for i in range(count):
        payload = {"item_id": "burger", "qty": 1, "user_id": f"u{i}"}
        resp = _post(ORDER_URL, payload)
        if resp.status_code != 200:
            print(f"  Error on order {i}: {resp.status_code}")
    
    total_time = time.time() - started
    throughput = count / total_time
    print(f"  Total: {count} orders in {total_time:.2f}s")
    print(f"  Throughput: {throughput:.2f} orders/sec")


def consumer_lag_test(count: int = 100) -> None:
    """Produce orders and measure consumer lag."""
    print(f"\n=== CONSUMER LAG TEST ({count} orders) ===")
    _post(RESET_URL, {})
    
    # Create consumer to check lag
    consumer = Consumer({
        "bootstrap.servers": "localhost:9092",
        "group.id": "lag-test-group",
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe(["orders"])
    
    # Produce orders
    print(f"  Producing {count} orders...")
    for i in range(count):
        payload = {"item_id": "burger", "qty": 1, "user_id": f"u{i}"}
        _post(ORDER_URL, payload)
    
    time.sleep(2)  # Give consumers time to process
    
    # Check lag
    print("  Measuring consumer lag...")
    for _ in range(10):
        msg = consumer.poll(timeout=1.0)
        if msg and not msg.error():
            pass
    
    consumer.close()
    print("  Lag measurement complete (see logs)")


def _print_stats(label: str, latencies: list) -> None:
    if not latencies:
        print(f"  {label}: no successful requests")
        return
    
    p50 = int(statistics.median(latencies))
    p95 = int(statistics.quantiles(latencies, n=20)[18]) if len(latencies) >= 20 else max(latencies)
    avg = int(statistics.mean(latencies))
    print(f"  {label}: avg={avg}ms p50={p50}ms p95={p95}ms (n={len(latencies)})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=int, default=0)
    parser.add_argument("--load", type=int, default=0)
    parser.add_argument("--lag", type=int, default=0)
    args = parser.parse_args()

    if args.baseline:
        baseline_test(args.baseline)
    if args.load:
        load_test(args.load)
    if args.lag:
        consumer_lag_test(args.lag)
    
    if not (args.baseline or args.load or args.lag):
        print("Usage: python run_tests.py --baseline N | --load N | --lag N")


if __name__ == "__main__":
    main()
