import json
import os
import sys
import uuid
import time
import pika
from datetime import datetime, timezone

from config import (RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASSWORD, RABBITMQ_VHOST,EXCHANGE_NAME, ORDER_PLACED_QUEUE,INVENTORY_RESERVED_ROUTING_KEY, INVENTORY_FAILED_ROUTING_KEY)
from models import OrderPlacedEvent, InventoryReservedEvent, InventoryFailedEvent

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
INVENTORY_PATH = os.path.join(DATA_DIR, "inventory.json")
PROCESSED_IDS_PATH = os.path.join(DATA_DIR, "processed_event_ids.json")


class InventoryService:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.inventory = self._load_inventory()
        self.processed_event_ids: set = self._load_processed_ids()
        self._connect()

    def _load_inventory(self) -> dict:
        if os.path.exists(INVENTORY_PATH):
            with open(INVENTORY_PATH) as f:
                return json.load(f)
        default = {"WIDGET-A": 100, "WIDGET-B": 50, "WIDGET-C": 25, "GADGET-X": 10}
        self._write_json(INVENTORY_PATH, default)
        return default

    def _load_processed_ids(self) -> set:
        if os.path.exists(PROCESSED_IDS_PATH):
            with open(PROCESSED_IDS_PATH) as f:
                return set(json.load(f))
        return set()

    def _save_processed_ids(self):
        self._write_json(PROCESSED_IDS_PATH, list(self.processed_event_ids))

    def _save_inventory(self):
        self._write_json(INVENTORY_PATH, self.inventory)

    @staticmethod
    def _write_json(path, data):
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def _log(msg):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] InventoryService | {msg}", flush=True)

    def _connect(self, retries=15, delay=2):
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
        params = pika.ConnectionParameters(
            host=RABBITMQ_HOST, port=RABBITMQ_PORT,
            virtual_host=RABBITMQ_VHOST, credentials=credentials,
        )
        for attempt in range(1, retries + 1):
            try:
                self.connection = pika.BlockingConnection(params)
                self.channel = self.connection.channel()
                self.channel.exchange_declare(
                    exchange=EXCHANGE_NAME, exchange_type="topic", durable=True
                )
                self.channel.basic_qos(prefetch_count=1)
                return
            except pika.exceptions.AMQPConnectionError:
                self._log(f"RabbitMQ not ready, retry {attempt}/{retries}")
                time.sleep(delay)
        raise RuntimeError("Cannot connect to RabbitMQ")

    # ── Consumer callback ─────────────────────────────────────────────
    def _on_order_placed(self, ch, method, properties, body):
        try:
            event = OrderPlacedEvent.from_json(body.decode("utf-8"))
            assert event.order_id, "missing order_id"
            assert event.customer_id, "missing customer_id"
            assert isinstance(event.items, list), "items must be a list"
            for item in event.items:
                assert "product_id" in item, "item missing product_id"
                assert "quantity" in item, "item missing quantity"
        except Exception as e:
            self._log(f"✘ MALFORMED message → DLQ | error: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        # Step 2: Idempotency check
        if event.event_id in self.processed_event_ids:
            self._log(
                f"⚡ DUPLICATE event_id={event.event_id:.36s} "
                f"for {event.order_id} → ACK (no-op, inventory unchanged)"
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        ok = True
        fail_reason = ""
        for item in event.items:
            pid = item["product_id"]
            qty = item["quantity"]
            available = self.inventory.get(pid, 0)
            if available < qty:
                ok = False
                fail_reason = f"Insufficient {pid}: need {qty}, have {available}"
                break

        if ok:
            for item in event.items:
                self.inventory[item["product_id"]] -= item["quantity"]
            self._save_inventory()

            res_id = f"RES-{uuid.uuid4().hex[:8].upper()}"
            out = InventoryReservedEvent(order_id=event.order_id, reservation_id=res_id)
            self.channel.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=INVENTORY_RESERVED_ROUTING_KEY,
                body=out.to_json(),
                properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
            )
            self._log(f"✔ RESERVED {event.order_id} | {res_id} | stock={self.inventory}")
        else:
            out = InventoryFailedEvent(order_id=event.order_id, reason=fail_reason)
            self.channel.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=INVENTORY_FAILED_ROUTING_KEY,
                body=out.to_json(),
                properties=pika.BasicProperties(delivery_mode=2, content_type="application/json"),
            )
            self._log(f"✘ FAILED {event.order_id} | {fail_reason}")

        # Step 4: Record event_id and ack
        self.processed_event_ids.add(event.event_id)
        self._save_processed_ids()
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        self.channel.basic_consume(
            queue=ORDER_PLACED_QUEUE,
            on_message_callback=self._on_order_placed,
            auto_ack=False,
        )
        self._log(f"Listening on '{ORDER_PLACED_QUEUE}'")
        self._log(f"Current stock: {self.inventory}")
        self._log(f"Previously processed events: {len(self.processed_event_ids)}")
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            self.channel.stop_consuming()
        self.connection.close()
        self._log("Stopped.")


if __name__ == "__main__":
    svc = InventoryService()
    svc.run()