import json
import os
import sys
import time
import uuid
import socket
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "broker"))
import pika
from config import (RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASSWORD,RABBITMQ_VHOST, EXCHANGE_NAME, ORDER_PLACED_ROUTING_KEY,ORDER_PLACED_QUEUE, DLQ_QUEUE)
from models import OrderPlacedEvent

DIVIDER = "=" * 72
PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")

# ── Helpers ───────────────────────────────────────────────────────────────

def rabbit_connection():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    return pika.BlockingConnection(pika.ConnectionParameters(
        host=RABBITMQ_HOST, port=RABBITMQ_PORT,
        virtual_host=RABBITMQ_VHOST, credentials=credentials,
    ))


def get_queue_depth(queue_name: str) -> int:
    conn = rabbit_connection()
    ch = conn.channel()
    result = ch.queue_declare(queue=queue_name, passive=True)
    depth = result.method.message_count
    conn.close()
    return depth


def publish_order(channel, customer_id, items, event_id=None):
    event = OrderPlacedEvent(
        order_id=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        customer_id=customer_id,
        items=items,
    )
    if event_id:
        event.event_id = event_id

    channel.basic_publish(
        exchange=EXCHANGE_NAME,
        routing_key=ORDER_PLACED_ROUTING_KEY,
        body=event.to_json(),
        properties=pika.BasicProperties(
            delivery_mode=2,
            content_type="application/json",
            message_id=event.event_id,
        ),
    )
    return event


def publish_raw(channel, body: str):
    channel.basic_publish(
        exchange=EXCHANGE_NAME,
        routing_key=ORDER_PLACED_ROUTING_KEY,
        body=body.encode("utf-8"),
        properties=pika.BasicProperties(
            delivery_mode=2,
            content_type="application/json",
            message_id=str(uuid.uuid4()),
        ),
    )


def docker_compose(*args):
    cmd = ["docker", "compose"] + list(args)
    result = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, text=True)
    return result


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] TEST | {msg}", flush=True)


# TEST 1: BACKLOG & RECOVERY
def test_backlog_and_recovery():
    print(f"\n{DIVIDER}")
    print("TEST 1: BACKLOG & RECOVERY")
    print(f"  Stop InventoryService for 60s, keep publishing, restart, drain")
    print(f"{DIVIDER}\n")

    # Stop inventory service
    log("Stopping inventory-service …")
    docker_compose("stop", "inventory-service")
    time.sleep(3)

    depth_before = get_queue_depth(ORDER_PLACED_QUEUE)
    log(f"Queue depth before publishing: {depth_before}")

    # Publish orders for 60 seconds
    PUBLISH_DURATION = 60  # seconds
    ORDER_INTERVAL = 1.0   # 1 order/sec

    conn = rabbit_connection()
    ch = conn.channel()
    ch.exchange_declare(exchange=EXCHANGE_NAME, exchange_type="topic", durable=True)

    log(f"Publishing orders for {PUBLISH_DURATION}s while InventoryService is DOWN …")
    products = ["WIDGET-A", "WIDGET-B", "WIDGET-C", "GADGET-X"]
    start = time.time()
    count = 0

    while time.time() - start < PUBLISH_DURATION:
        product = products[count % len(products)]
        evt = publish_order(ch, f"CUST-{count+1:03d}", [{"product_id": product, "quantity": 1}])
        count += 1
        if count % 10 == 0:
            depth = get_queue_depth(ORDER_PLACED_QUEUE)
            log(f"  published {count} orders … queue depth: {depth}")
        time.sleep(ORDER_INTERVAL)

    conn.close()

    backlog = get_queue_depth(ORDER_PLACED_QUEUE)
    log(f"Done publishing. Total orders: {count}")
    log(f"Queue depth (backlog): {backlog}")

    # Restart inventory service
    print()
    log("Restarting inventory-service — watching backlog drain …")
    docker_compose("start", "inventory-service")

    # Poll until drained
    poll_start = time.time()
    while time.time() - poll_start < 120:
        time.sleep(3)
        depth = get_queue_depth(ORDER_PLACED_QUEUE)
        log(f"  Queue depth: {depth}")
        if depth == 0:
            log("✔ Backlog fully drained!")
            break
    else:
        log("⚠ Timed out waiting for drain")

    # Show inventory-service logs
    print()
    log("Inventory service logs (last 30 lines):")
    result = docker_compose("logs", "--tail=30", "inventory-service")
    print(result.stdout)

    print(f"\n{'─'*72}")
    log("TEST 1 COMPLETE ✓")


# TEST 2: IDEMPOTENCY
def test_idempotency():
    print(f"\n{DIVIDER}")
    print("TEST 2: IDEMPOTENCY — duplicate event_id must not double-reserve")
    print(f"{DIVIDER}\n")

    # Get current inventory via docker exec
    log("Reading current inventory …")
    result = docker_compose("exec", "-T", "inventory-service", "cat", "/app/data/inventory.json")
    if result.returncode == 0:
        stock_before = json.loads(result.stdout)
    else:
        stock_before = {"WIDGET-A": 100, "WIDGET-B": 50, "WIDGET-C": 25, "GADGET-X": 10}
    log(f"Stock before: {stock_before}")
    widget_a_before = stock_before.get("WIDGET-A", 0)

    # Publish the SAME event TWICE with identical event_id
    fixed_event_id = str(uuid.uuid4())
    conn = rabbit_connection()
    ch = conn.channel()
    ch.exchange_declare(exchange=EXCHANGE_NAME, exchange_type="topic", durable=True)

    for i in range(2):
        evt = OrderPlacedEvent(
            order_id="ORD-IDEMPOTENT",
            customer_id="CUST-IDEM",
            items=[{"product_id": "WIDGET-A", "quantity": 5}],
            event_id=fixed_event_id,
        )
        ch.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=ORDER_PLACED_ROUTING_KEY,
            body=evt.to_json(),
            properties=pika.BasicProperties(
                delivery_mode=2, content_type="application/json",
                message_id=evt.event_id,
            ),
        )
        log(f"Published OrderPlaced #{i+1} with event_id={fixed_event_id}")
    conn.close()

    # Wait for processing
    log("Waiting for InventoryService to process …")
    time.sleep(8)

    # Check stock after
    result = docker_compose("exec", "-T", "inventory-service", "cat", "/app/data/inventory.json")
    stock_after = json.loads(result.stdout) if result.returncode == 0 else stock_before
    widget_a_after = stock_after.get("WIDGET-A", 0)
    deducted = widget_a_before - widget_a_after

    log(f"Stock after : {stock_after}")
    log(f"WIDGET-A deducted: {deducted}  (expected 5; would be 10 if double-reserved)")

    if deducted == 5:
        log("✔ IDEMPOTENCY VERIFIED — only one reservation made")
    else:
        log(f"✘ IDEMPOTENCY ISSUE — deducted {deducted}")

    # Show the duplicate detection in logs
    print()
    log("InventoryService logs showing DUPLICATE detection:")
    result = docker_compose("logs", "--tail=10", "inventory-service")
    print(result.stdout)

    print(f"\n{'─'*72}")
    log("TEST 2 COMPLETE ✓")


# TEST 3: DLQ / POISON MESSAGES
def test_dlq_poison():
    print(f"\n{DIVIDER}")
    print("TEST 3: DLQ / POISON MESSAGE HANDLING")
    print(f"{DIVIDER}\n")

    conn = rabbit_connection()
    ch = conn.channel()
    ch.exchange_declare(exchange=EXCHANGE_NAME, exchange_type="topic", durable=True)

    poison_msgs = [
        ("not valid json at all {{{{", "invalid JSON"),
        ('{"order_id": "X"}', "missing required fields (customer_id, items, …)"),
        ('{"order_id":"Y","customer_id":"C","items":"not_a_list",'
         '"event_id":"bad-1","timestamp":"now","event_type":"OrderPlaced"}',
         "items is wrong type (string instead of list)"),
    ]

    for body, desc in poison_msgs:
        publish_raw(ch, body)
        log(f"Published poison: {desc}")

    conn.close()

    log("Waiting for InventoryService to reject …")
    time.sleep(8)

    # Check DLQ
    dlq_depth = get_queue_depth(DLQ_QUEUE)
    log(f"DLQ depth: {dlq_depth}")

    if dlq_depth > 0:
        log("✔ Poison messages routed to DLQ")
    else:
        log("✘ DLQ empty — check configuration")

    # Peek at DLQ contents
    conn2 = rabbit_connection()
    ch2 = conn2.channel()
    print()
    log("DLQ contents:")
    for i in range(10):
        method, props, body = ch2.basic_get(queue=DLQ_QUEUE, auto_ack=False)
        if method is None:
            break
        body_preview = body.decode("utf-8", errors="replace")[:80]
        x_death = ""
        if props.headers and "x-death" in props.headers:
            reason = props.headers["x-death"][0].get("reason", "unknown")
            queue = props.headers["x-death"][0].get("queue", "unknown")
            x_death = f" | reason={reason}, orig_queue={queue}"
        log(f"  DLQ #{i+1}: {body_preview}{x_death}")
        ch2.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    conn2.close()

    # Show InventoryService logs
    print()
    log("InventoryService logs showing MALFORMED rejections:")
    result = docker_compose("logs", "--tail=10", "inventory-service")
    print(result.stdout)

    print(f"\n{'─'*72}")
    log("TEST 3 COMPLETE ✓")


# MAIN
if __name__ == "__main__":
    print(DIVIDER)
    print("ASYNC RABBITMQ — FULL TEST SUITE")
    print(f"Time : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Host : RABBITMQ_HOST={RABBITMQ_HOST}")
    print(DIVIDER)

    # Ensure stack is up
    log("Verifying Docker Compose stack …")
    result = docker_compose("ps", "--format", "json")
    if result.returncode != 0:
        print("ERROR: docker compose not running. Run 'docker compose up -d' first.")
        sys.exit(1)

    test_backlog_and_recovery()
    test_idempotency()
    test_dlq_poison()

    print(f"\n{DIVIDER}")
    print("ALL TESTS COMPLETE")
    print(DIVIDER)