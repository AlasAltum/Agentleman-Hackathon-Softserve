FROM python:3.12-slim

ENV POETRY_VERSION=1.8.5 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /workspace/observability/test
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root

WORKDIR /workspace/observability/test
CMD ["sleep", "infinity"]