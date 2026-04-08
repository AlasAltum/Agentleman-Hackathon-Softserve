FROM python:3.12-slim AS builder

RUN apt-get update && \
    apt-get install --no-install-suggests --no-install-recommends --yes pipx

ENV PATH="/root/.local/bin:${PATH}"

RUN pipx install poetry
RUN pipx inject poetry poetry-plugin-bundle

WORKDIR /src
COPY . .

RUN poetry bundle venv --python=/usr/local/bin/python3 --only=main /venv

FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONPATH=/app/src
ENV APP_ENV=prod

COPY --from=builder /venv /venv

COPY --from=builder /src /app
WORKDIR /app

RUN apt-get update && \
    rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["/venv/bin/python", "src/api/entrypoint.py"]