import json
import os
import sys
import uuid
import time
import socket
import threading
import pika
from datetime import datetime, timezone

from config import (RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASSWORD, RABBITMQ_VHOST,EXCHANGE_NAME, ORDER_PLACED_ROUTING_KEY)
from models import OrderPlacedEvent

LOCAL_STORE = os.path.join(os.path.dirname(__file__), "data", "orders.json")
COMMAND_PORT = int(os.environ.get("COMMAND_PORT", "9001"))


class OrderService:
    def __init__(self):
        self.orders: dict = {}
        self._load_store()
        self._connect_rabbit()

    def _connect_rabbit(self, retries=15, delay=2):
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
                return
            except pika.exceptions.AMQPConnectionError:
                self._log(f"RabbitMQ not ready, retry {attempt}/{retries}")
                time.sleep(delay)
        raise RuntimeError("Cannot connect to RabbitMQ")

    def _load_store(self):
        os.makedirs(os.path.dirname(LOCAL_STORE), exist_ok=True)
        if os.path.exists(LOCAL_STORE):
            with open(LOCAL_STORE) as f:
                self.orders = json.load(f)

    def _save_store(self):
        os.makedirs(os.path.dirname(LOCAL_STORE), exist_ok=True)
        with open(LOCAL_STORE, "w") as f:
            json.dump(self.orders, f, indent=2)

    @staticmethod
    def _log(msg):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] OrderService | {msg}", flush=True)

    def place_order(self, customer_id: str, items: list[dict],
                    force_event_id: str = None) -> OrderPlacedEvent:
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        event = OrderPlacedEvent(
            order_id=order_id,
            customer_id=customer_id,
            items=items,
        )
        if force_event_id:
            event.event_id = force_event_id

        self.orders[order_id] = {
            "order_id": order_id,
            "customer_id": customer_id,
            "items": items,
            "status": "PLACED",
            "created_at": event.timestamp,
        }
        self._save_store()

        self.channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=ORDER_PLACED_ROUTING_KEY,
            body=event.to_json(),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
                message_id=event.event_id,
            ),
        )
        self._log(f"PLACED {order_id} | event_id={event.event_id}")
        return event

    def publish_raw(self, body: str):
        self.channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=ORDER_PLACED_ROUTING_KEY,
            body=body.encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
                message_id=str(uuid.uuid4()),
            ),
        )
        self._log("PUBLISHED RAW (possibly malformed)")

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()


def command_listener(svc: OrderService):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", COMMAND_PORT))
    srv.listen(5)
    svc._log(f"Command socket on :{COMMAND_PORT}")

    while True:
        conn, _ = srv.accept()
        data = conn.recv(4096).decode("utf-8").strip()
        response = "OK"
        try:
            if data.startswith("place "):
                parts = data.split()
                customer_id = parts[1]
                items = []
                for item_str in parts[2].split(","):
                    prod, qty = item_str.split(":")
                    items.append({"product_id": prod, "quantity": int(qty)})
                force_eid = parts[3] if len(parts) > 3 else None
                evt = svc.place_order(customer_id, items, force_event_id=force_eid)
                response = json.dumps({"order_id": evt.order_id, "event_id": evt.event_id})
            elif data.startswith("raw "):
                svc.publish_raw(data[4:])
            elif data == "ping":
                response = "pong"
            else:
                response = f"ERR unknown command: {data}"
        except Exception as e:
            response = f"ERR {e}"
        conn.sendall(response.encode("utf-8"))
        conn.close()


if __name__ == "__main__":
    svc = OrderService()
    t = threading.Thread(target=command_listener, args=(svc,), daemon=True)
    t.start()
    svc._log("Running (TCP commands + stdin). Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        svc.close()
        svc._log("Stopped.")