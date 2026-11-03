# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TABFERRY_DATA_DIR=/data

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY tabferry ./tabferry

RUN pip install --no-cache-dir .

VOLUME ["/data"]
EXPOSE 8123

ENTRYPOINT ["tabferry"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8123"]
