FROM python:3.12-slim

LABEL authors="toni"

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt \
    && chmod +x /app/deploy/cloud-entrypoint.sh

ENTRYPOINT ["/app/deploy/cloud-entrypoint.sh"]