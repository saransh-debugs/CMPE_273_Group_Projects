from pydantic import BaseModel


class OrderRequest(BaseModel):
    item_id: str
    qty: int
    user_id: str
    order_id: str | None = None


class OrderResponse(BaseModel):
    order_id: str
    status: str
    latency_ms: int


class ConfigRequest(BaseModel):
    inventory_timeout_s: float | None = None
    notification_timeout_s: float | None = None
