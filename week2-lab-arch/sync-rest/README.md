# Sync REST workflow

This part implements the campus food ordering workflow using synchronous REST calls.
OrderService calls InventoryService to reserve stock, then calls NotificationService
to send a confirmation. All services share the same SQLite database from common/.

## What is in this folder

- docker-compose.yml
	- Brings up OrderService (8000), InventoryService (8001), NotificationService (8002).
	- Mounts ../common/db/shared.db into each container at /data/shared.db.

- order_service/
	- app.py: FastAPI app startup and router wiring.
	- routes.py: /health, /config, /order workflow and error handling.
	- models.py: Pydantic request/response models.

- inventory_service/
	- app.py: FastAPI app startup and router wiring.
	- routes.py: /health, /config, /reserve, /reset (reset data for tests).
	- models.py: Pydantic request models.

- notification_service/
	- app.py: FastAPI app startup and router wiring.
	- routes.py: /health, /send (idempotent send).
	- models.py: Pydantic request models.

- tests/
	- run_tests.py: Baseline latency, injected 2s delay, injected timeout failure.
	- README.md: Short test instructions.

## Quick start (Docker)

```bash
docker compose up --build
```

Services:
- OrderService: http://localhost:8000
- InventoryService: http://localhost:8001
- NotificationService: http://localhost:8002

### Sanity checks

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
```

### Create a sample order

```bash
curl -X POST http://localhost:8000/order \
	-H "Content-Type: application/json" \
	-d '{"item_id":"burger","qty":1,"user_id":"u1"}'
```

## Local venv (for tests)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Tests

The test runner resets the shared database before each phase and then measures
latency and error handling.

```bash
python3 tests/run_tests.py --baseline 50
python3 tests/run_tests.py --delay 50
python3 tests/run_tests.py --failure 10
```

## Output table (sample)

Use your measured values in this table.

| Test case | Avg latency | P50 | P95 | Notes |
| --- | --- | --- | --- | --- |
| Baseline | 15ms | 15ms | 25ms | No injected delay or failure |
| Inventory delay 2s | 2045ms | 2046ms | 2050ms | Order latency includes inventory delay |
| Inventory timeout | n/a | n/a | n/a | 10/10 returned 504 timeout |

## Why this behavior happens

- Synchronous REST makes OrderService wait for InventoryService and NotificationService.
- Adding 2s to inventory adds roughly 2s to total order latency.
- When inventory is forced to timeout, OrderService hits its timeout and returns 504.
- The reset endpoint clears state so tests run with full inventory and no prior orders.
