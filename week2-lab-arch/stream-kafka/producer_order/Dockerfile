FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY stream-kafka/producer_order/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app and common
COPY stream-kafka/producer_order/ .
COPY common/ ../common/

ENV PYTHONPATH=/app:../

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
