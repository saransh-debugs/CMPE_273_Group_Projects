# Kafka Streaming: Campus Food Ordering

This implementation demonstrates the same order-inventory-notification workflow using **Apache Kafka** for event streaming, enabling asynchronous, decoupled service communication.

## Architecture

```
┌─────────────────────────────────────────────────┐
│          Kafka Cluster (3 Topics)               │
├─────────────────────────────────────────────────┤
│  - orders (OrderPlaced events)                  │
│  - inventory-events (InventoryReserved/Failed)  │
│  - metrics (Analytics output)                   │
└─────────────────────────────────────────────────┘
  ▲         ▲         ▲
  │         │         │
  │ pub  │ sub+pub  │ sub
  │         │         │
┌─┴──┐  ┌──┴──┐   ┌──┴────┐
│ Ord│  │Inv. │   │Analyt.│
│    │  │Cons│   │Cons. │
└────┘  └─────┘   └───────┘
```

## Services

### 1. **Producer (Order Service)** — Port 8000
- **Endpoint**: `POST /order`
- Stores order in SQLite
- Publishes `OrderPlaced` event to `orders` topic
- Returns immediately (async)

**Sample request:**
```bash
curl -X POST http://localhost:8000/order \
  -H "Content-Type: application/json" \
  -d '{"item_id":"burger","qty":1,"user_id":"u1"}'
```

### 2. **Inventory Consumer**
- Consumes `OrderPlaced` events from `orders` topic
- Checks stock and reserves if available
- Publishes `InventoryReserved` or `InventoryFailed` to `inventory-events` topic
- **Idempotency**: Deduplicates by order_id (no double-reserve)

### 3. **Analytics Consumer**
- Consumes from both `orders` and `inventory-events` topics
- Computes metrics every 60s:
  - Orders per minute (OPM)
  - Failure rate (%)
- Supports consumer offset reset for replay validation

## Running

### Start Services
```bash
cd stream-kafka
docker compose up --build
```

Wait for all services to be healthy (Kafka, Zookeeper, producers, consumers).

### Test Scenarios

Install test dependencies:
```bash
pip install -r tests/requirements.txt
```

**Baseline Latency (50 orders):**
```bash
python tests/run_tests.py --baseline 50
```

**Load Test (1000 rapid orders):**
```bash
python tests/run_tests.py --load 1000
```

**Consumer Lag (100 orders):**
```bash
python tests/run_tests.py --lag 100
```

## Key Features

✅ **Event Sourcing** — Full audit trail of all events
✅ **Idempotency** — Duplicate messages don't double-reserve inventory
✅ **Replay Capability** — Reset consumer offsets and recompute metrics
✅ **Decoupled Services** — No direct calls between services
✅ **Scalability** — Kafka naturally handles high throughput

## Topics & Schemas

| Topic | Schema |
|---|---|
| `orders` | `{order_id, item_id, qty, user_id, timestamp}` |
| `inventory-events` | `{order_id, item_id, status, qty, timestamp}` |

## Expected Behavior

1. **Order Created** → stored in DB, event published
2. **Inventory Processed** → stock checked, reservation created (or failed)
3. **Metrics Computed** → OPM and failure rate calculated every 60s
4. **Replay** → reset consumer group offset, metrics recomputed identically

## Testing Observability

### View Kafka Topics
```bash
docker exec -it stream-kafka-kafka-1 kafka-topics --list --bootstrap-server localhost:9092
```

### Consume Topic Messages
```bash
docker exec -it stream-kafka-kafka-1 kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic orders \
  --from-beginning
```

### Check Consumer Group Lag
```bash
docker exec -it stream-kafka-kafka-1 kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --group inventory-group \
  --describe
```

## Notes

- Services are resilient to broker restarts
- Consumers use `auto.offset.reset=earliest` to catch up on restart
- All state is persisted in the shared SQLite DB and Kafka topics
