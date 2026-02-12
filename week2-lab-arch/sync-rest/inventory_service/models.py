from pydantic import BaseModel


class ReserveRequest(BaseModel):
    order_id: str
    item_id: str
    qty: int


class ConfigRequest(BaseModel):
    delay_ms: int | None = None
    fail_mode: str | None = None
    fail_code: int | None = None
