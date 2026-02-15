FROM python:3.11-slim

WORKDIR /app

COPY stream-kafka/inventory_consumer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY stream-kafka/inventory_consumer/ .
COPY common/ ../common/

ENV PYTHONPATH=/app:../

CMD ["python", "app.py"]
