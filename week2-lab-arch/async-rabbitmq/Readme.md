# Async RabbitMQ — Submission

**Author:** Saransh  
**Date:** 2026-02-15  
**Stack:** Python 3.12 · pika · RabbitMQ 3 · SQLite (WAL) · Docker Compose

---

## Architecture Overview

```
OrderService ──OrderPlaced──▶ InventoryService ──InventoryReserved──▶ NotificationService
                                    │
                                    ├── InventoryFailed ──────────────▶ NotificationService
                                    │
                              nack(requeue=False)
                                    │
                                    ▼
                               Dead Letter Queue
```

All services share a single SQLite database (`common/db/shared.db`) with tables for `orders`, `inventory`, `reservations`, `notifications`, and `processed_events`. RabbitMQ provides the async message bus using a topic exchange with dead-letter routing.

---

## Test Results (Run 3 — 2026-02-15 22:29:07)

All three tests **passed**.

---

## Test 1: Backlog & Recovery

**Goal:** Prove that messages are durably queued when a consumer is down, and fully processed once it comes back.

**Procedure:**

1. Stop InventoryService
2. Publish 60 orders over 60 seconds (1/sec)
3. Observe queue depth growing
4. Restart InventoryService
5. Confirm queue drains to 0

### Logs — Publishing Phase (InventoryService DOWN)

```
[22:29:07] TEST | Stopping inventory-service …
[22:29:11] TEST | Queue depth before publishing: 0
[22:29:11] TEST | Publishing orders for 60s while InventoryService is DOWN …
[22:29:21] TEST |   published 10 orders … queue depth: 10
[22:29:31] TEST |   published 20 orders … queue depth: 20
[22:29:41] TEST |   published 30 orders … queue depth: 30
[22:29:51] TEST |   published 40 orders … queue depth: 40
[22:30:01] TEST |   published 50 orders … queue depth: 50
[22:30:11] TEST |   published 60 orders … queue depth: 60
[22:30:12] TEST | Done publishing. Total orders: 60
[22:30:12] TEST | Queue depth (backlog): 60
```

### Logs — Recovery Phase (InventoryService restarted)

```
[22:30:12] TEST | Restarting inventory-service — watching backlog drain …
[22:30:17] TEST |   Queue depth: 0
[22:30:17] TEST | ✔ Backlog fully drained!
```

### Logs — InventoryService Processing (sample of drain)

```
inventory-service-1  | ✔ RESERVED ORD-D3515FD7 | RES-4811D3BC | stock={'WIDGET-A': 50, 'WIDGET-B': 11, ...}
inventory-service-1  | ✔ RESERVED ORD-FA7716B1 | RES-666FC4A7 | stock={'WIDGET-A': 50, 'WIDGET-B': 10, ...}
inventory-service-1  | ✘ FAILED ORD-93A5CBA9 | Insufficient WIDGET-C: need 1, have 0
inventory-service-1  | ✘ FAILED ORD-484A4D86 | Insufficient GADGET-X: need 1, have 0
inventory-service-1  | ✔ RESERVED ORD-25BB2062 | RES-2DC035DC | stock={'WIDGET-A': 49, 'WIDGET-B': 10, ...}
  ... (60 messages total — all processed)
inventory-service-1  | ✔ RESERVED ORD-59EAF861 | RES-185C4A6F | stock={'WIDGET-A': 45, 'WIDGET-B': 5, ...}
inventory-service-1  | ✘ FAILED ORD-9FC994A2 | Insufficient GADGET-X: need 1, have 0
```

**Result: ✔ PASS** — 60 messages queued while consumer was down. All 60 drained within ~5 seconds of restart. Zero data loss.

---

## Test 2: Idempotency

**Goal:** Prove that redelivering the same `OrderPlaced` message does not cause a double reservation.

**Procedure:**

1. Record current stock level
2. Create one `OrderPlaced` event (qty=5 WIDGET-A) with a fixed `event_id`
3. Publish the **exact same event twice** to the queue
4. Let InventoryService process both copies
5. Verify stock was deducted only **once** (5, not 10)

### Logs

```
[22:30:17] TEST | Stock before: {'WIDGET-A': 45, 'WIDGET-B': 5, 'WIDGET-C': 0, 'GADGET-X': 0}
[22:30:17] TEST | Published OrderPlaced #1 with event_id=f1e91e52-e8c2-4dfe-85df-20f2aac954b6
[22:30:17] TEST | Published OrderPlaced #2 with event_id=f1e91e52-e8c2-4dfe-85df-20f2aac954b6
[22:30:17] TEST | Waiting for InventoryService to process …
[22:30:26] TEST | Stock after : {'WIDGET-A': 40, 'WIDGET-B': 5, 'WIDGET-C': 0, 'GADGET-X': 0}
[22:30:26] TEST | WIDGET-A deducted: 5  (expected 5; would be 10 if double-reserved)
[22:30:26] TEST | ✔ IDEMPOTENCY VERIFIED — only one reservation made
```

### InventoryService Logs — Duplicate Detection

```
inventory-service-1  | ✔ RESERVED ORD-IDEMPOTENT | RES-444CB792 | stock={'WIDGET-A': 40, ...}
inventory-service-1  | ⚡ DUPLICATE event_id=f1e91e52-e8c2-4dfe-85df-20f2aac954b6
                       for ORD-IDEMPOTENT → ACK (no-op, inventory unchanged)
```

First copy: reserved successfully (WIDGET-A 45 → 40). Second copy: detected as duplicate, acknowledged with no-op. Stock unchanged.

**Result: ✔ PASS** — Deducted 5, not 10.

---

## Test 3: DLQ / Poison Message Handling

**Goal:** Prove that malformed messages are rejected to the Dead Letter Queue without crashing the consumer.

**Procedure:**

1. Publish 3 malformed messages: invalid JSON, missing required fields, wrong field type
2. Let InventoryService attempt to parse each one
3. Confirm all land in the DLQ with `reason=rejected`

### Logs

```
[22:30:26] TEST | Published poison: invalid JSON
[22:30:26] TEST | Published poison: missing required fields (customer_id, items, …)
[22:30:26] TEST | Published poison: items is wrong type (string instead of list)
[22:30:26] TEST | Waiting for InventoryService to reject …
[22:30:34] TEST | DLQ depth: 9
[22:30:34] TEST | ✔ Poison messages routed to DLQ
```

> DLQ depth = 9 because poison messages from the two earlier test runs (3 per run) accumulated in the queue. The 3 new rejections from this run are confirmed by the InventoryService logs below.

### InventoryService Logs — Malformed Rejections

```
inventory-service-1  | ✘ MALFORMED message → DLQ | error: Expecting value: line 1 column 1 (char 0)
inventory-service-1  | ✘ MALFORMED message → DLQ | error: OrderPlacedEvent.__init__() missing 2
                       required positional arguments: 'customer_id' and 'items'
inventory-service-1  | ✘ MALFORMED message → DLQ | error: items must be a list
```

Each malformed message was `nack(requeue=False)` → routed via the dead-letter exchange (`order_events_dlx`) → landed in the DLQ (`order_events_dlq`). The consumer continued processing normally after each rejection.

**Result: ✔ PASS** — All 3 poison messages rejected to DLQ. Consumer unaffected.

---

## Idempotency Strategy Explanation

### Problem

RabbitMQ provides **at-least-once** delivery. If InventoryService processes a message but crashes before sending the ACK back to the broker, RabbitMQ will redeliver that message. Without protection, inventory gets deducted twice for the same order.

### Solution: `processed_events` Table with Transactional Write

Every `OrderPlaced` event carries a unique `event_id` (UUID) assigned by OrderService at publish time. InventoryService checks a `processed_events` table in SQLite before doing any work:

```
receive message
     │
     ▼
parse JSON ──── fail ──▶ nack(requeue=False) → DLQ
     │
     ▼
SELECT FROM processed_events WHERE event_id = ?
     │                │
   EXISTS          NOT EXISTS
     │                │
     ▼                ▼
   ACK           BEGIN TRANSACTION
  (no-op)          UPDATE inventory SET quantity = quantity - ?
                   INSERT INTO reservations (...)
                   INSERT INTO processed_events (event_id, ...)
                 COMMIT
                 publish InventoryReserved
                 ACK
```

### Why It Works

1. **Deterministic ID:** The `event_id` is set by the producer, so redelivered copies of the same message carry the identical UUID.

2. **Atomic dedup + business write:** The `INSERT INTO processed_events` and `UPDATE inventory` happen in the **same SQLite transaction**. Either both succeed or neither does. There is no window where inventory is deducted but the event isn't marked as processed.

3. **Crash safety:** If the service crashes after COMMIT but before ACK, the broker redelivers the message. On the next attempt, the `SELECT` finds the `event_id` already in `processed_events` and skips straight to ACK — no double deduction.

4. **Proof from test logs:**
   - First delivery: `✔ RESERVED ORD-IDEMPOTENT` (stock 45 → 40)
   - Second delivery: `⚡ DUPLICATE event_id=f1e91e52-... → ACK (no-op, inventory unchanged)`
   - Final stock: 40 (deducted 5, not 10)

### Schema

```sql
CREATE TABLE IF NOT EXISTS processed_events (
  event_id TEXT PRIMARY KEY,
  processed_at TEXT NOT NULL
);
```

### Production Considerations

For a production system at higher scale, this SQLite table could be replaced with a Redis `SET` with TTL for O(1) lookups with auto-expiry, or a PostgreSQL column with a `UNIQUE` constraint inside the same transaction as the business write. The core principle — check before processing, persist the event ID atomically with the side effect — remains the same regardless of storage backend.