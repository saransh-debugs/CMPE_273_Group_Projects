import time
import pika
from config import (RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASSWORD, RABBITMQ_VHOST,EXCHANGE_NAME, EXCHANGE_TYPE, DLX_EXCHANGE, DLQ_QUEUE,ORDER_PLACED_QUEUE, ORDER_PLACED_ROUTING_KEY,INVENTORY_RESERVED_QUEUE, INVENTORY_RESERVED_ROUTING_KEY,INVENTORY_FAILED_QUEUE, INVENTORY_FAILED_ROUTING_KEY)


def connect_with_retry(max_retries=15, delay=2):
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST, port=RABBITMQ_PORT,
        virtual_host=RABBITMQ_VHOST, credentials=credentials,
    )
    for attempt in range(1, max_retries + 1):
        try:
            return pika.BlockingConnection(params)
        except pika.exceptions.AMQPConnectionError:
            print(f"[setup] RabbitMQ not ready, retry {attempt}/{max_retries} …")
            time.sleep(delay)
    raise RuntimeError("Could not connect to RabbitMQ")


def setup_infrastructure():
    connection = connect_with_retry()
    channel = connection.channel()

    # Dead Letter Exchange & Queue
    channel.exchange_declare(exchange=DLX_EXCHANGE, exchange_type="fanout", durable=True)
    channel.queue_declare(queue=DLQ_QUEUE, durable=True)
    channel.queue_bind(queue=DLQ_QUEUE, exchange=DLX_EXCHANGE)
    print(f"[setup] DLX '{DLX_EXCHANGE}' → DLQ '{DLQ_QUEUE}'")

    # Main Exchange
    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type=EXCHANGE_TYPE, durable=True)
    print(f"[setup] Exchange '{EXCHANGE_NAME}' ({EXCHANGE_TYPE})")

    # Queues with dead-letter routing
    dlx_args = {"x-dead-letter-exchange": DLX_EXCHANGE}

    for queue, routing_key in [
        (ORDER_PLACED_QUEUE, ORDER_PLACED_ROUTING_KEY),
        (INVENTORY_RESERVED_QUEUE, INVENTORY_RESERVED_ROUTING_KEY),
        (INVENTORY_FAILED_QUEUE, INVENTORY_FAILED_ROUTING_KEY),
    ]:
        channel.queue_declare(queue=queue, durable=True, arguments=dlx_args)
        channel.queue_bind(queue=queue, exchange=EXCHANGE_NAME, routing_key=routing_key)
        print(f"[setup] Queue '{queue}' ← '{routing_key}'")

    connection.close()
    print("[setup] Infrastructure ready ✓")


if __name__ == "__main__":
    setup_infrastructure()