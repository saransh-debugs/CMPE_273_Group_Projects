import logging
from consumer import InventoryConsumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Start the inventory consumer."""
    consumer = InventoryConsumer(bootstrap_servers="kafka:9092", group_id="inventory-group")
    consumer.start()
    consumer.run()


if __name__ == "__main__":
    main()
