FROM python:3.12-slim

WORKDIR /app

RUN mkdir -p /app/logs && pip install --no-cache-dir nats-py httpx

COPY main.py .

CMD ["python", "main.py"]
