import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from common import db as common_db

from models import ConfigRequest, ReserveRequest

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/config")
def set_config(config: ConfigRequest, request: Request) -> dict:
    if config.delay_ms is not None:
        request.app.state.delay_ms = config.delay_ms
    if config.fail_mode is not None:
        request.app.state.fail_mode = config.fail_mode
    if config.fail_code is not None:
        request.app.state.fail_code = config.fail_code
    return {
        "delay_ms": request.app.state.delay_ms,
        "fail_mode": request.app.state.fail_mode,
        "fail_code": request.app.state.fail_code,
    }


@router.post("/reset")
def reset_state() -> dict:
    conn = common_db.connect()
    try:
        conn.execute("DELETE FROM reservations")
        conn.execute("DELETE FROM notifications")
        conn.execute("DELETE FROM orders")
        conn.execute("UPDATE inventory SET quantity = 100")
        conn.commit()
    finally:
        conn.close()

    return {"status": "reset"}


@router.post("/reserve")
def reserve_item(payload: ReserveRequest, request: Request) -> dict:
    # Injection points used by the latency and failure tests.
    if request.app.state.delay_ms > 0:
        time.sleep(request.app.state.delay_ms / 1000)

    if request.app.state.fail_mode == "error":
        raise HTTPException(status_code=request.app.state.fail_code, detail="Injected failure")

    if request.app.state.fail_mode == "timeout":
        time.sleep(10)

    conn = common_db.connect()
    try:
        existing = conn.execute(
            "SELECT order_id FROM reservations WHERE order_id = ?",
            (payload.order_id,),
        ).fetchone()
        if existing:
            # Idempotency for duplicate reservation requests.
            return {"status": "already_reserved", "order_id": payload.order_id}

        row = conn.execute(
            "SELECT quantity FROM inventory WHERE item_id = ?",
            (payload.item_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        if row[0] < payload.qty:
            raise HTTPException(status_code=409, detail="Insufficient stock")

        conn.execute(
            "UPDATE inventory SET quantity = quantity - ? WHERE item_id = ?",
            (payload.qty, payload.item_id),
        )
        conn.execute(
            "INSERT INTO reservations (order_id, item_id, qty, reserved_at) VALUES (?, ?, ?, ?)",
            (
                payload.order_id,
                payload.item_id,
                payload.qty,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {"status": "reserved", "order_id": payload.order_id}
