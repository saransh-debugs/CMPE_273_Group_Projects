import json
import time
import logging
from confluent_kafka import Producer
from confluent_kafka.error import KafkaException

logger = logging.getLogger(__name__)


class OrderProducer:
    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        self.bootstrap_servers = bootstrap_servers
        self.producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "acks": "all",  # All replicas must acknowledge
            "retries": 3,
        })

    def delivery_report(self, err, msg):
        """Callback for message delivery success/failure."""
        if err is not None:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.info(f"Message delivered to {msg.topic()} [{msg.partition()}]")

    def publish_order_event(self, order_event: dict) -> bool:
        """
        Publish OrderPlaced event to Kafka.
        
        Args:
            order_event: {order_id, item_id, qty, user_id, timestamp}
        
        Returns:
            True if published successfully, False otherwise
        """
        try:
            message_json = json.dumps(order_event)
            self.producer.produce(
                topic="orders",
                key=order_event["order_id"].encode("utf-8"),
                value=message_json.encode("utf-8"),
                callback=self.delivery_report,
            )
            self.producer.flush(timeout=5)
            return True
        except KafkaException as e:
            logger.error(f"Kafka error publishing order: {e}")
            return False
        except Exception as e:
            logger.error(f"Error publishing order: {e}")
            return False

    def close(self):
        """Close producer connection."""
        self.producer.flush()
