import os
import logging
from consumer import InventoryConsumer
from common import db as common_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    common_db.init_db()
    """Start the inventory consumer."""
    bootstrap = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
    group_id = os.getenv("GROUP_ID", "inventory-group")
    logger.info(f"Starting InventoryConsumer with KAFKA_BOOTSTRAP={bootstrap} GROUP_ID={group_id}")

    consumer = InventoryConsumer(bootstrap_servers=bootstrap, group_id=group_id)
    consumer.run()  # run() should call start() internally or you can call start() then run()

if __name__ == "__main__":
    main()
