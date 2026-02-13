from pydantic import BaseModel


class MetricsSnapshot(BaseModel):
    timestamp: float
    orders_per_minute: float
    failure_rate: float
    total_orders: int
    failed_orders: int
