from pydantic import BaseModel
from typing import Optional


class OrderPlacedEvent(BaseModel):
    order_id: str
    item_id: str
    qty: int
    user_id: str
    timestamp: float


class InventoryEvent(BaseModel):
    order_id: str
    item_id: str
    status: str  # "reserved" or "failed"
    qty: int
    timestamp: float
