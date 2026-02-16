FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir pika
COPY async-rabbitmq/order_service /app/
COPY common /app/common
ENV PYTHONPATH=/app
CMD ["python", "-u", "app.py"]