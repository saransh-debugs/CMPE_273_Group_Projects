import uuid


def new_order_id() -> str:
    # Short deterministic prefix for easy log scanning.
    return f"ord_{uuid.uuid4().hex[:12]}"
