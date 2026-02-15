import os
import time
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from common import db as common_db
from common.ids import new_order_id

from models import OrderRequest, OrderResponse
from producer import OrderProducer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="OrderProducer")

# Initialize Kafka producer
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
producer = OrderProducer(bootstrap_servers=KAFKA_BOOTSTRAP)


@app.on_event("startup")
def startup() -> None:
    """Initialize DB on startup."""
    common_db.init_db()
    logger.info(f"Connected to Kafka: {KAFKA_BOOTSTRAP}")


@app.on_event("shutdown")
def shutdown() -> None:
    """Close producer on shutdown."""
    producer.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/order", response_model=OrderResponse)
def create_order(order: OrderRequest) -> OrderResponse:
    """
    Create order and publish to Kafka.
    
    Steps:
    1. Generate order_id
    2. Store order in local DB with status "pending"
    3. Publish OrderPlaced event to Kafka
    4. Return immediately (async)
    """
    order_id = order.order_id or new_order_id()
    timestamp = time.time()

    # Store order in local DB
    conn = common_db.connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO orders (order_id, item_id, qty, user_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, order.item_id, order.qty, order.user_id, "pending", timestamp),
        )
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"DB error: {e}")
    finally:
        conn.close()

    # Publish to Kafka
    event = {
        "order_id": order_id,
        "item_id": order.item_id,
        "qty": order.qty,
        "user_id": order.user_id,
        "timestamp": timestamp,
    }

    if not producer.publish_order_event(event):
        raise HTTPException(status_code=502, detail="Failed to publish to Kafka")

    return OrderResponse(
        order_id=order_id,
        status="published",
        message="Order published to event stream",
    )


@app.post("/reset")
def reset_state() -> dict:
    """Reset DB for testing."""
    conn = common_db.connect()
    try:
        conn.execute("DELETE FROM orders")
        conn.execute("DELETE FROM reservations")
        conn.execute("DELETE FROM notifications")
        conn.execute("UPDATE inventory SET quantity = 100")
        conn.commit()
    finally:
        conn.close()
    return {"status": "reset"}
