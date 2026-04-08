FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir mlflow==3.2.0

WORKDIR /mlflow

EXPOSE 5000