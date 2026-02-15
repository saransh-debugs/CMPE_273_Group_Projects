import json
import time
import logging
from collections import defaultdict
from confluent_kafka import Consumer
from confluent_kafka.error import KafkaError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnalyticsConsumer:
    def __init__(self, bootstrap_servers: str = "localhost:9092", group_id: str = "analytics-group"):
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })
        
        # Metrics tracking
        self.total_orders = 0
        self.failed_orders = 0
        self.window_start = time.time()
        self.last_report = time.time()
        self.metrics_history = []

    def start(self):
        """Subscribe to both orders and inventory-events topics."""
        max_retries = 10
        for attempt in range(max_retries):
            try:
                self.consumer.subscribe(["orders", "inventory-events"])
                logger.info("Subscribed to 'orders' and 'inventory-events' topics")
                return
            except Exception as e:
                logger.warning(f"Attempt {attempt+1}/{max_retries} to subscribe failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
        raise Exception("Failed to subscribe after max retries")

    def compute_and_report_metrics(self, force: bool = False):
        """Compute and report metrics every 60s."""
        now = time.time()
        elapsed = now - self.window_start
        
        # Report every 60s or on force
        if elapsed >= 60 or force:
            opm = (self.total_orders / elapsed * 60) if elapsed > 0 else 0
            failure_rate = (self.failed_orders / self.total_orders * 100) if self.total_orders > 0 else 0
            
            metrics = {
                "timestamp": now,
                "orders_per_minute": round(opm, 2),
                "failure_rate": round(failure_rate, 2),
                "total_orders": self.total_orders,
                "failed_orders": self.failed_orders,
            }
            
            self.metrics_history.append(metrics)
            logger.info(f"METRICS: {metrics}")
            
            # Reset window
            self.window_start = now
            self.total_orders = 0
            self.failed_orders = 0

    def process_message(self, topic: str, message: dict):
        """Process incoming message from Kafka."""
        if topic == "orders":
            self.total_orders += 1
            logger.debug(f"Order event: {message.get('order_id')}")
        elif topic == "inventory-events":
            if message.get("status") == "failed":
                self.failed_orders += 1
            logger.debug(f"Inventory event: {message.get('order_id')} -> {message.get('status')}")

    def run(self):
        """Main consumer loop."""
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    self.compute_and_report_metrics()
                    continue
                
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error(f"Consumer error: {msg.error()}")
                        continue
                
                try:
                    topic = msg.topic()
                    payload = json.loads(msg.value().decode("utf-8"))
                    self.process_message(topic, payload)
                    self.consumer.commit(asynchronous=False)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        except KeyboardInterrupt:
            logger.info("Consumer interrupted")
            self.compute_and_report_metrics(force=True)
            self.print_metrics_summary()
        finally:
            self.consumer.close()

    def print_metrics_summary(self):
        """Print accumulated metrics."""
        logger.info("\n=== METRICS SUMMARY ===")
        for m in self.metrics_history:
            logger.info(f"  {m}")

    def get_metrics_history(self):
        """Return collected metrics for external use."""
        return self.metrics_history
