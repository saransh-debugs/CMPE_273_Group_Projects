import os
import json
import time
import logging
from collections import defaultdict

from confluent_kafka import Consumer, KafkaError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("analytics_consumer")


def minute_bucket(ts: float) -> int:
    """Return epoch minute bucket start (e.g., 1771322100)."""
    ts = float(ts)
    return int(ts // 60) * 60


class AnalyticsConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str = "analytics-group"):
        self.bootstrap = bootstrap_servers
        self.group_id = group_id

        self.orders_topic = os.getenv("ORDERS_TOPIC", "orders")
        self.inventory_topic = os.getenv("INVENTORY_EVENTS_TOPIC", "inventory-events")

        # How often to print metrics
        self.print_every_sec = int(os.getenv("METRICS_PRINT_EVERY_SEC", "10"))

        # Replay-safe aggregates
        self.orders_per_minute = defaultdict(int)  # minute_bucket -> count
        self.inventory_total = 0
        self.inventory_failed = 0

        # Optional: de-dup by order_id during replay (not strictly required if upstream is clean)
        # Helps if you accidentally re-deliver the same record.
        self.seen_orders = set()
        self.seen_inventory = set()

        self.consumer = Consumer({
            "bootstrap.servers": self.bootstrap,
            "group.id": self.group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,

            # Helps avoid session timeout if processing/printing is slow
            "session.timeout.ms": 45000,
            "max.poll.interval.ms": 600000,
        })

    def start(self):
        # Subscribe to both topics in one consumer
        self.consumer.subscribe([self.orders_topic, self.inventory_topic])
        logger.info(f"Subscribed to topics: {self.orders_topic}, {self.inventory_topic}")
        logger.info(f"bootstrap={self.bootstrap} group_id={self.group_id}")

    def _handle_order(self, event: dict):
        if event.get("type") != "OrderPlaced":
            return

        order_id = event.get("order_id")
        if order_id and order_id in self.seen_orders:
            return
        if order_id:
            self.seen_orders.add(order_id)

        ts = event.get("timestamp", time.time())
        b = minute_bucket(ts)
        self.orders_per_minute[b] += 1

    def _handle_inventory(self, event: dict):
        etype = event.get("type")
        if etype not in ("InventoryReserved", "InventoryFailed"):
            return

        order_id = event.get("order_id")
        if order_id and order_id in self.seen_inventory:
            return
        if order_id:
            self.seen_inventory.add(order_id)

        self.inventory_total += 1
        if etype == "InventoryFailed":
            self.inventory_failed += 1

    def _print_metrics(self):
        total_orders = sum(self.orders_per_minute.values())
        failure_rate = (self.inventory_failed / self.inventory_total) if self.inventory_total else 0.0

        # Print top few minute buckets (sorted)
        buckets = sorted(self.orders_per_minute.items())
        last_few = buckets[-5:] if len(buckets) > 5 else buckets

        metrics = {
            "timestamp": time.time(),
            "total_orders": total_orders,
            "inventory_outcomes": self.inventory_total,
            "failed_orders": self.inventory_failed,
            "failure_rate": round(failure_rate, 4),
            "orders_per_minute_last_few": last_few,
        }
        logger.info(f"METRICS: {metrics}")

    def run(self):
        self.start()
        last_print = time.time()

        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)

                now = time.time()
                if now - last_print >= self.print_every_sec:
                    self._print_metrics()
                    last_print = now

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error(f"Consumer error: {msg.error()}")
                    continue

                try:
                    payload = json.loads(msg.value().decode("utf-8"))

                    topic = msg.topic()
                    if topic == self.orders_topic:
                        self._handle_order(payload)
                    elif topic == self.inventory_topic:
                        self._handle_inventory(payload)

                    # Commit only after successful processing
                    self.consumer.commit(message=msg, asynchronous=False)

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    # Skip poison messages
                    self.consumer.commit(message=msg, asynchronous=False)
                except Exception as e:
                    logger.exception(f"Processing error: {e}")
                    # Do NOT commit on unknown error; retry

        except KeyboardInterrupt:
            logger.info("Interrupted")
        finally:
            self.consumer.close()
