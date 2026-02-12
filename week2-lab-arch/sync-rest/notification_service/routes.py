from datetime import datetime, timezone

from fastapi import APIRouter

from common import db as common_db

from models import SendRequest

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/send")
def send_notification(payload: SendRequest) -> dict:
    conn = common_db.connect()
    try:
        existing = conn.execute(
            "SELECT order_id FROM notifications WHERE order_id = ?",
            (payload.order_id,),
        ).fetchone()
        if existing:
            # Idempotency for repeated send attempts.
            return {"status": "already_sent", "order_id": payload.order_id}

        conn.execute(
            "INSERT INTO notifications (order_id, user_id, message, sent_at) VALUES (?, ?, ?, ?)",
            (
                payload.order_id,
                payload.user_id,
                payload.message,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {"status": "sent", "order_id": payload.order_id}
