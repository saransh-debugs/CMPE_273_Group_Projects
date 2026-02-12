FROM python:3.11-slim

WORKDIR /app

COPY sync-rest/notification_service/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY sync-rest/notification_service /app/
COPY common /app/common

ENV PYTHONPATH=/app

EXPOSE 8002
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
