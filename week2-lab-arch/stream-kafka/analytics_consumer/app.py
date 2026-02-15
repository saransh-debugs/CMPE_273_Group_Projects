import logging
from consumer import AnalyticsConsumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Start the analytics consumer."""
    consumer = AnalyticsConsumer(bootstrap_servers="kafka:9092", group_id="analytics-group")
    consumer.start()
    consumer.run()


if __name__ == "__main__":
    main()
