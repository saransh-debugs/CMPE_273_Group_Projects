import os
import logging
from consumer import AnalyticsConsumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Start the analytics consumer."""
    bootstrap = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
    group_id = os.getenv("GROUP_ID", "analytics-group")
    logger.info(f"Starting AnalyticsConsumer with KAFKA_BOOTSTRAP={bootstrap} GROUP_ID={group_id}")

    consumer = AnalyticsConsumer(bootstrap_servers=bootstrap, group_id=group_id)
    consumer.start()
    consumer.run()

if __name__ == "__main__":
    main()
