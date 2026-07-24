# syntax=docker/dockerfile:1

FROM python:3.11-slim

# Prevent .pyc files, force stdout/stderr to be unbuffered (so `koyeb service logs` shows output live)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps: none needed beyond build-essential for a couple of wheels that
# don't ship manylinux binaries on slim images; kept minimal on purpose.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Koyeb injects the port to listen on via the PORT env var (defaults to 8000
# for local `docker run`). The app reads PORT itself in app/config.py, and
# this CMD passes it straight to uvicorn.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
