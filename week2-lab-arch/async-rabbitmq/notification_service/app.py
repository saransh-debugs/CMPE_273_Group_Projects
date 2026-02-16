import json
import os
import time
import pika
from datetime import datetime, timezone

from config import (RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASSWORD, RABBITMQ_VHOST,EXCHANGE_NAME, INVENTORY_RESERVED_QUEUE, INVENTORY_FAILED_QUEUE)
from models import InventoryReservedEvent, InventoryFailedEvent

LOG_PATH = os.path.join(os.path.dirname(__file__), "logs", "notifications.log")


class NotificationService:
    def __init__(self):
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        self._connect()

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
                self.channel.basic_qos(prefetch_count=5)
                return
            except pika.exceptions.AMQPConnectionError:
                self._log(f"RabbitMQ not ready, retry {attempt}/{retries}")
                time.sleep(delay)
        raise RuntimeError("Cannot connect to RabbitMQ")

    def _log(self, msg):
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        line = f"[{ts}] NotificationService | {msg}"
        print(line, flush=True)
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")

    def _on_reserved(self, ch, method, properties, body):
        try:
            event = InventoryReservedEvent.from_json(body.decode("utf-8"))
            self._log(f"📧 CONFIRMATION sent for {event.order_id} | res={event.reservation_id}")
        except Exception as e:
            self._log(f"✘ MALFORMED InventoryReserved → DLQ | {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def _on_failed(self, ch, method, properties, body):
        try:
            event = InventoryFailedEvent.from_json(body.decode("utf-8"))
            self._log(f"📧 FAILURE notice for {event.order_id} | reason={event.reason}")
        except Exception as e:
            self._log(f"✘ MALFORMED InventoryFailed → DLQ | {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        self.channel.basic_consume(
            queue=INVENTORY_RESERVED_QUEUE,
            on_message_callback=self._on_reserved,
            auto_ack=False,
        )
        self.channel.basic_consume(
            queue=INVENTORY_FAILED_QUEUE,
            on_message_callback=self._on_failed,
            auto_ack=False,
        )
        self._log(f"Listening on '{INVENTORY_RESERVED_QUEUE}' + '{INVENTORY_FAILED_QUEUE}'")
        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            self.channel.stop_consuming()
        self.connection.close()
        self._log("Stopped.")


if __name__ == "__main__":
    svc = NotificationService()
    svc.run()