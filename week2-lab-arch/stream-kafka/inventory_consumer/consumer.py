import json
import time
import logging
from confluent_kafka import Consumer, Producer
from confluent_kafka.error import KafkaError

from common import db as common_db
from models import OrderPlacedEvent, InventoryEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class InventoryConsumer:
    def __init__(self, bootstrap_servers: str = "localhost:9092", group_id: str = "inventory-group"):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        
        # Consumer config
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })
        
        # Producer for inventory events
        self.producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "acks": "all",
        })
        
        # Track processed orders for idempotency
        self.processed_orders = set()

    def start(self):
        """Subscribe to orders topic and begin consuming."""
        max_retries = 10
        for attempt in range(max_retries):
            try:
                self.consumer.subscribe(["orders"])
                logger.info("Subscribed to 'orders' topic")
                return
            except Exception as e:
                logger.warning(f"Attempt {attempt+1}/{max_retries} to subscribe failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
        raise Exception("Failed to subscribe after max retries")

    def process_message(self, message: dict) -> bool:
        """
        Process an order and emit inventory event.
        
        Idempotency: Skip if order_id already processed.
        """
        order_id = message.get("order_id")
        
        # Idempotency check
        if order_id in self.processed_orders:
            logger.info(f"Order {order_id} already processed, skipping")
            return True
        
        item_id = message.get("item_id")
        qty = message.get("qty")
        timestamp = time.time()
        
        # Check inventory
        conn = common_db.connect()
        try:
            row = conn.execute(
                "SELECT quantity FROM inventory WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            
            if not row:
                status = "failed"
                detail = "Item not found"
            elif row[0] < qty:
                status = "failed"
                detail = f"Insufficient stock: {row[0]} available, {qty} requested"
            else:
                # Reserve inventory
                conn.execute(
                    "UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?",
                    (qty, item_id),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO reservations (order_id, item_id, qty, reserved_at) VALUES (?, ?, ?, ?)",
                    (order_id, item_id, qty, time.time()),
                )
                conn.commit()
                status = "reserved"
                detail = "Inventory reserved"
        except Exception as e:
            logger.error(f"DB error processing order {order_id}: {e}")
            status = "failed"
            detail = str(e)
        finally:
            conn.close()
        
        # Publish inventory event
        event = {
            "order_id": order_id,
            "item_id": item_id,
            "status": status,
            "qty": qty,
            "timestamp": timestamp,
        }
        
        try:
            self.producer.produce(
                topic="inventory-events",
                key=order_id.encode("utf-8"),
                value=json.dumps(event).encode("utf-8"),
            )
            self.producer.flush(timeout=5)
            logger.info(f"Published inventory event: {order_id} -> {status}")
        except Exception as e:
            logger.error(f"Failed to publish inventory event: {e}")
            return False
        
        # Mark as processed
        self.processed_orders.add(order_id)
        return True

    def run(self):
        """Main consumer loop."""
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    continue
                
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error(f"Consumer error: {msg.error()}")
                        continue
                
                try:
                    payload = json.loads(msg.value().decode("utf-8"))
                    logger.info(f"Received order: {payload}")
                    self.process_message(payload)
                    self.consumer.commit(asynchronous=False)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    self.consumer.commit(asynchronous=False)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        except KeyboardInterrupt:
            logger.info("Consumer interrupted")
        finally:
            self.consumer.close()
            self.producer.flush()

    def process_message(self, message: dict) -> bool:
        """
        Process an order and emit inventory event.
        
        Idempotency: Skip if order_id already processed.
        """
        order_id = message.get("order_id")
        
        # Idempotency check
        if order_id in self.processed_orders:
            logger.info(f"Order {order_id} already processed, skipping")
            return True
        
        item_id = message.get("item_id")
        qty = message.get("qty")
        timestamp = time.time()
        
        # Check inventory
        conn = common_db.connect()
        try:
            row = conn.execute(
                "SELECT quantity FROM inventory WHERE item_id = ?",
                (item_id,),
            ).fetchone()
            
            if not row:
                status = "failed"
                detail = "Item not found"
            elif row[0] < qty:
                status = "failed"
                detail = f"Insufficient stock: {row[0]} available, {qty} requested"
            else:
                # Reserve inventory
                conn.execute(
                    "UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?",
                    (qty, item_id),
                )
                conn.execute(
                    "INSERT OR REPLACE INTO reservations (order_id, item_id, qty, reserved_at) VALUES (?, ?, ?, ?)",
                    (order_id, item_id, qty, time.time()),
                )
                conn.commit()
                status = "reserved"
                detail = "Inventory reserved"
        except Exception as e:
            logger.error(f"DB error processing order {order_id}: {e}")
            status = "failed"
            detail = str(e)
        finally:
            conn.close()
        
        # Publish inventory event
        event = {
            "order_id": order_id,
            "item_id": item_id,
            "status": status,
            "qty": qty,
            "timestamp": timestamp,
        }
        
        try:
            self.producer.produce(
                topic="inventory-events",
                key=order_id.encode("utf-8"),
                value=json.dumps(event).encode("utf-8"),
            )
            self.producer.flush(timeout=5)
            logger.info(f"Published inventory event: {order_id} -> {status}")
        except Exception as e:
            logger.error(f"Failed to publish inventory event: {e}")
            return False
        
        # Mark as processed
        self.processed_orders.add(order_id)
        return True

    def run(self):
        """Main consumer loop."""
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    continue
                
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error(f"Consumer error: {msg.error()}")
                        continue
                
                try:
                    payload = json.loads(msg.value().decode("utf-8"))
                    logger.info(f"Received order: {payload}")
                    self.process_message(payload)
                    self.consumer.commit(asynchronous=False)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    self.consumer.commit(asynchronous=False)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        except KeyboardInterrupt:
            logger.info("Consumer interrupted")
        finally:
            self.consumer.close()
            self.producer.flush()
