import os
import time
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, HTTPException, Request

from common import db as common_db
from common.ids import new_order_id

from models import ConfigRequest, OrderRequest, OrderResponse

router = APIRouter()

INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://localhost:8001")
NOTIFICATION_URL = os.environ.get("NOTIFICATION_URL", "http://localhost:8002")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/config")
def set_config(config: ConfigRequest, request: Request) -> dict:
    if config.inventory_timeout_s is not None:
        request.app.state.inventory_timeout_s = config.inventory_timeout_s
    if config.notification_timeout_s is not None:
        request.app.state.notification_timeout_s = config.notification_timeout_s
    return {
        "inventory_timeout_s": request.app.state.inventory_timeout_s,
        "notification_timeout_s": request.app.state.notification_timeout_s,
    }


@router.post("/order", response_model=OrderResponse)
def create_order(order: OrderRequest, request: Request) -> OrderResponse:
    started = time.time()
    order_id = order.order_id or new_order_id()
    created_at = datetime.now(timezone.utc).isoformat()

    conn = common_db.connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO orders (order_id, item_id, qty, user_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, order.item_id, order.qty, order.user_id, "created", created_at),
        )
        conn.commit()
    finally:
        conn.close()

    inventory_payload = {
        "order_id": order_id,
        "item_id": order.item_id,
        "qty": order.qty,
    }

    try:
        resp = requests.post(
            f"{INVENTORY_URL}/reserve",
            json=inventory_payload,
            timeout=request.app.state.inventory_timeout_s,
        )
    except requests.Timeout as exc:
        _update_order_status(order_id, "inventory_timeout")
        raise HTTPException(status_code=504, detail="Inventory timeout") from exc
    except requests.RequestException as exc:
        _update_order_status(order_id, "inventory_error")
        raise HTTPException(status_code=502, detail="Inventory error") from exc

    if resp.status_code != 200:
        _update_order_status(order_id, "inventory_failed")
        raise HTTPException(status_code=502, detail=resp.json().get("error", "Inventory failed"))

    # Notification is only sent after inventory reservation succeeds.
    notify_payload = {
        "order_id": order_id,
        "user_id": order.user_id,
        "message": f"Order {order_id} confirmed",
    }

    try:
        notify_resp = requests.post(
            f"{NOTIFICATION_URL}/send",
            json=notify_payload,
            timeout=request.app.state.notification_timeout_s,
        )
        notify_resp.raise_for_status()
    except requests.RequestException as exc:
        _update_order_status(order_id, "notification_failed")
        raise HTTPException(status_code=502, detail="Notification failed") from exc

    _update_order_status(order_id, "completed")

    latency_ms = int((time.time() - started) * 1000)
    return OrderResponse(order_id=order_id, status="completed", latency_ms=latency_ms)


def _update_order_status(order_id: str, status: str) -> None:
    conn = common_db.connect()
    try:
        conn.execute(
            "UPDATE orders SET status = ? WHERE order_id = ?",
            (status, order_id),
        )
        conn.commit()
    finally:
        conn.close()
