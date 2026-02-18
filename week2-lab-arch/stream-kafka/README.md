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

#### Producer publishes OrderEvents stream: OrderPlaced
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.39.22 AM.png>) 
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.39.32 AM.png>) 

#### Inventory consumes and emits InventoryEvents
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.39.41 AM.png>) 

#### Analytics consumes streams and computes
  1. Placed two orders
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.39.53 AM.png>) 

  2. docker logs -f stream-kafka-analytics_consumer-1

![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.40.06 AM.png>) 

#### Demonstrate replay 
  1. Place order for 50
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.40.18 AM.png>)

  2. Before reset Inventory-order logs/metrics
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.40.25 AM.png>)

  3. Reset Inventory-order logs/metrics
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.40.34 AM.png>)

  4. After Reset - Reset analytics offsets back to earliest 
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.40.44 AM.png>)


 #### Testing requirements
  1. Produce 10k events
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.42.19 AM.png>)

![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.42.46 AM.png>)

    a.  Metrics for the same  
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.42.57 AM.png>)

    b. Total orders is ~ 10,000 events. Here, you see events > 10k because there were few orders already. 
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.43.10 AM.png>)

  2. Show consumer lag under throttling = 20
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.43.29 AM.png>)
  
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.43.39 AM.png>)

  3. Show replay producing consistent metrics (or explain why not)
    a. Before replay - Analytics consumer is inactive
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.43.49 AM.png>)

    b. Reset offsets
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.44.05 AM.png>)

    c. After Reset
![alt text](<test_screenshots/Screenshot 2026-02-18 at 12.44.16 AM.png>) 


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
