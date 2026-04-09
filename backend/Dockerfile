FROM python:3.12-slim AS builder

RUN apt-get update && \
    apt-get install --no-install-suggests --no-install-recommends --yes pipx

ENV PATH="/root/.local/bin:${PATH}"

RUN pipx install poetry
RUN pipx inject poetry poetry-plugin-bundle

WORKDIR /src
COPY . .

RUN python3 -m venv /venv

# 2. Establecemos las variables de entorno para "activar" el venv. 
# Así Poetry sabrá que debe instalar todo aquí adentro en lugar de crear uno propio.
ENV VIRTUAL_ENV=/venv \
    PATH="/venv/bin:$PATH"

# 3. Usamos el comando nativo de poetry install, que SÍ reconoce --extras
RUN poetry install --only main --extras all

FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app
ENV APP_ENV=prod

COPY --from=builder /venv /venv

COPY --from=builder /src /app
WORKDIR /app

RUN apt-get update && \
    rm -rf /var/lib/apt/lists/*

CMD ["/bin/sh", "-c", "\
    echo 'Waiting for Qdrant...' && \
    until /venv/bin/python -c \"\
import os, urllib.request; \
base = os.getenv('QDRANT_URL', 'http://qdrant:6333').rstrip('/'); \
urllib.request.urlopen(base + '/healthz') \
\" 2>/dev/null; do sleep 1; done && \
    echo 'Seeding Qdrant...' && \
    /venv/bin/python -m src.qdrant_setup.setup && \
    echo 'Starting backend...' && \
    exec /venv/bin/python -m uvicorn src.api.entrypoint:app --host 0.0.0.0 --port 8000"]