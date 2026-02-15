from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class OrderRequest(BaseModel):
    item_id: str
    qty: int
    user_id: str
    order_id: Optional[str] = None


class OrderResponse(BaseModel):
    order_id: str
    status: str
    message: str


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
