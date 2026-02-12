# Sync REST tests

Run tests after `docker compose up --build`.

```bash
python tests/run_tests.py --baseline 50
python tests/run_tests.py --delay 50
python tests/run_tests.py --failure 10
```
