import os
import json
import time
import logging
from confluent_kafka import Consumer, Producer, KafkaError

from common import db as common_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("inventory_consumer")


class InventoryConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str = "inventory-group"):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id

        self.orders_topic = os.getenv("ORDERS_TOPIC", "orders")
        self.inventory_events_topic = os.getenv("INVENTORY_EVENTS_TOPIC", "inventory-events")
        self.throttle_ms = int(os.getenv("THROTTLE_MS", "0"))

        logger.info(f"InventoryConsumer init: bootstrap={self.bootstrap_servers} group_id={self.group_id} "
                    f"orders_topic={self.orders_topic} inventory_topic={self.inventory_events_topic} throttle_ms={self.throttle_ms}")

        # Consumer (manual commit)
        self.consumer = Consumer({
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": self.group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })

        # Producer for inventory events
        self.producer = Producer({
            "bootstrap.servers": self.bootstrap_servers,
            "acks": "all",
            "retries": 3,
        })

    def start(self):
        """Subscribe to orders topic."""
        max_retries = 6
        for attempt in range(max_retries):
            try:
                self.consumer.subscribe([self.orders_topic])
                logger.info(f"Subscribed to '{self.orders_topic}'")
                return
            except Exception as e:
                logger.warning(f"Subscribe attempt {attempt+1}/{max_retries} failed: {e}")
                time.sleep(2)
        raise RuntimeError("Failed to subscribe to topic")

    def _already_processed(self, conn, order_id: str) -> bool:
        r = conn.execute("SELECT 1 FROM reservations WHERE order_id = ? LIMIT 1", (order_id,)).fetchone()
        return r is not None

    def _publish_inventory_event(self, event: dict) -> bool:
        try:
            key = str(event.get("order_id", "unknown")).encode("utf-8")
            value = json.dumps(event).encode("utf-8")
            self.producer.produce(topic=self.inventory_events_topic, key=key, value=value)
            self.producer.flush(timeout=5)
            logger.info(f"Published inventory event: {event.get('order_id')} -> {event.get('type')}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish inventory event: {e}")
            return False

    def process_message(self, message: dict) -> bool:
        """
        Durable idempotency: check reservations table for order_id.
        Commit consumer offset only after _publish_inventory_event returns True.
        """
        order_id = message.get("order_id")
        item_id = message.get("item_id")
        qty = message.get("qty")

        if self.throttle_ms > 0:
            time.sleep(self.throttle_ms / 1000.0)

        if not order_id or not item_id or qty is None:
            logger.error("Malformed order message: %s", message)
            ev = {
                "type": "InventoryFailed",
                "order_id": order_id or "unknown",
                "item_id": item_id or "unknown",
                "qty": qty if qty is not None else -1,
                "status": "failed",
                "timestamp": time.time(),
                "reason": "malformed_order",
            }
            return self._publish_inventory_event(ev)

        qty = int(qty)
        ts = float(message.get("timestamp", time.time()))
        user_id = message.get("user_id", "unknown")

        conn = common_db.connect()
        try:
            conn.execute("BEGIN")
            if self._already_processed(conn, order_id):
                # Emit a reserved event (idempotent) and do not change stock
                ev = {
                    "type": "InventoryReserved",
                    "order_id": order_id,
                    "item_id": item_id,
                    "qty": qty,
                    "status": "reserved",
                    "timestamp": ts,
                    "note": "duplicate_order_id",
                }
                conn.commit()
                return self._publish_inventory_event(ev)

            row = conn.execute("SELECT quantity FROM inventory WHERE item_id = ?", (item_id,)).fetchone()
            if not row:
                # record reservation as failed for idempotency
                conn.execute(
                    "INSERT OR REPLACE INTO reservations(order_id, item_id, qty, reserved_at, status) VALUES (?, ?, ?, ?, ?)",
                    (order_id, item_id, qty, time.time(), "failed"),
                )
                conn.commit()
                ev = {
                    "type": "InventoryFailed",
                    "order_id": order_id,
                    "item_id": item_id,
                    "qty": qty,
                    "status": "failed",
                    "timestamp": ts,
                    "reason": "item_not_found",
                }
                return self._publish_inventory_event(ev)

            available = int(row[0])
            if available < qty:
                conn.execute(
                    "INSERT OR REPLACE INTO reservations(order_id, item_id, qty, reserved_at, status) VALUES (?, ?, ?, ?, ?)",
                    (order_id, item_id, qty, time.time(), "failed"),
                )
                conn.commit()
                ev = {
                    "type": "InventoryFailed",
                    "order_id": order_id,
                    "item_id": item_id,
                    "qty": qty,
                    "status": "failed",
                    "timestamp": ts,
                    "reason": f"out_of_stock:{available}",
                }
                return self._publish_inventory_event(ev)

            # reserve: decrement stock + record reservation
            conn.execute("UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?", (qty, item_id))
            conn.execute(
                "INSERT OR REPLACE INTO reservations(order_id, item_id, qty, reserved_at, status) VALUES (?, ?, ?, ?, ?)",
                (order_id, item_id, qty, time.time(), "reserved"),
            )
            conn.commit()

            ev = {
                "type": "InventoryReserved",
                "order_id": order_id,
                "item_id": item_id,
                "qty": qty,
                "status": "reserved",
                "timestamp": ts,
            }
            return self._publish_inventory_event(ev)

        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.exception("DB error processing order %s: %s", order_id, e)
            ev = {
                "type": "InventoryFailed",
                "order_id": order_id,
                "item_id": item_id,
                "qty": qty,
                "status": "failed",
                "timestamp": ts,
                "reason": f"db_error:{e}",
            }
            return self._publish_inventory_event(ev)
        finally:
            conn.close()

    def run(self):
        """Main loop. commit offsets only after successful publish"""
        self.start()
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error("Consumer error: %s", msg.error())
                    continue

                try:
                    payload = json.loads(msg.value().decode("utf-8"))
                    logger.info("Received order: %s", payload)
                    ok = self.process_message(payload)

                    if ok:
                        # commit offset only after successful publish
                        self.consumer.commit(message=msg, asynchronous=False)
                    else:
                        logger.warning("Publish failed; not committing offset so message will be retried")

                except json.JSONDecodeError as e:
                    logger.error("JSON decode error: %s", e)
                    # commit to skip bad message (or change behavior to send to DLQ)
                    self.consumer.commit(message=msg, asynchronous=False)
                except Exception as e:
                    logger.exception("Unexpected processing error: %s", e)
                    # do not commit so message will be retried
        except KeyboardInterrupt:
            logger.info("Interrupted")
        finally:
            try:
                self.consumer.close()
            finally:
                self.producer.flush()


if __name__ == "__main__":
    # Read bootstrap from env (default to kafka:29092 inside compose)
    bootstrap = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
    group = os.getenv("GROUP_ID", "inventory-group")
    # Optional: show env for debugging
    logger.info(f"Starting InventoryConsumer with BOOTSTRAP={bootstrap} GROUP_ID={group}")
    InventoryConsumer(bootstrap_servers=bootstrap, group_id=group).run()
