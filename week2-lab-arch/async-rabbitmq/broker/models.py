import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import List


@dataclass
class OrderPlacedEvent:
    order_id: str
    customer_id: str
    items: List[dict]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str = "OrderPlaced"

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "OrderPlacedEvent":
        d = json.loads(data)
        return cls(**d)


@dataclass
class InventoryReservedEvent:
    order_id: str
    reservation_id: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str = "InventoryReserved"

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "InventoryReservedEvent":
        d = json.loads(data)
        return cls(**d)


@dataclass
class InventoryFailedEvent:
    order_id: str
    reason: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str = "InventoryFailed"

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> "InventoryFailedEvent":
        d = json.loads(data)
        return cls(**d)