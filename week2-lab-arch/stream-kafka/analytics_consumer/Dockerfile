FROM python:3.11-slim

WORKDIR /app

COPY stream-kafka/analytics_consumer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY stream-kafka/analytics_consumer/ .

CMD ["python", "app.py"]
