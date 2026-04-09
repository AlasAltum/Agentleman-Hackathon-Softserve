FROM python:3.12-slim

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MLFLOW_VERSION=3.11.1

# Install MLflow with extras for better tracing support
RUN pip install --no-cache-dir \
    mlflow==${MLFLOW_VERSION} \
    boto3 \
    psycopg2-binary

# Create directories with proper permissions
RUN mkdir -p /mlflow/artifacts \
             /mlflow/mlruns \
             /mlflow/models \
    && chmod -R 777 /mlflow

WORKDIR /mlflow

# Create non-root user for security
RUN useradd -m -u 1000 mlflow \
    && chown -R mlflow:mlflow /mlflow

USER mlflow

# Expose MLflow port
EXPOSE 5000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Default command
# --default-artifact-root mlflow-artifacts:// → clients use HTTP proxy (no direct filesystem access needed)
# --artifacts-destination /mlflow/artifacts  → server stores files here internally
# --serve-artifacts                          → server acts as artifact proxy
CMD ["mlflow", "server", \
     "--host", "0.0.0.0", \
     "--port", "5000", \
     "--backend-store-uri", "sqlite:////mlflow/mlflow.db", \
     "--artifacts-destination", "/mlflow/artifacts", \
     "--default-artifact-root", "mlflow-artifacts://", \
     "--serve-artifacts"]