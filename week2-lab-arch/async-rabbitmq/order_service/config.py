import os

RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = 5672
RABBITMQ_USER = "guest"
RABBITMQ_PASSWORD = "guest"
RABBITMQ_VHOST = "/"

# Exchange
EXCHANGE_NAME = "order_events"
EXCHANGE_TYPE = "topic"

# Queues & routing keys
ORDER_PLACED_QUEUE = "inventory.order_placed"
ORDER_PLACED_ROUTING_KEY = "order.placed"

INVENTORY_RESERVED_QUEUE = "notification.inventory_reserved"
INVENTORY_RESERVED_ROUTING_KEY = "inventory.reserved"

INVENTORY_FAILED_QUEUE = "notification.inventory_failed"
INVENTORY_FAILED_ROUTING_KEY = "inventory.failed"

# Dead-letter
DLX_EXCHANGE = "order_events_dlx"
DLQ_QUEUE = "order_events_dlq"