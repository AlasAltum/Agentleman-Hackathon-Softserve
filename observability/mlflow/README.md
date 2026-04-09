This directory contains the local MLflow service image used by the observability stack.

Current purpose:
- run a local MLflow tracking server for traces and experiment browsing
- keep the setup simple for hackathon development

Current runtime behavior:
- backend store: SQLite at `/mlflow/mlflow.db`
- artifact root: `/mlflow/artifacts`
- exposed port: `5001`

The actual trace-producing scripts will be added in later tasks under `observability/test`.