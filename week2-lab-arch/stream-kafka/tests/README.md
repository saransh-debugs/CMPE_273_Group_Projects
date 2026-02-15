# Kafka Streaming Tests

## Quick Start

```bash
# From workspace root
cd stream-kafka

# Start all services
docker compose up --build

# In another terminal, run tests
python tests/run_tests.py --baseline 50
python tests/run_tests.py --load 1000
python tests/run_tests.py --lag 100
```

## Test Descriptions

- **baseline**: Produce N orders with normal latency
- **load**: Rapid-fire N orders to measure throughput
- **lag**: Produce N orders and measure consumer lag
