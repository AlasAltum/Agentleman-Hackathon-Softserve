#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RESTART_STACK="false"
OBSERVABILITY_SERVICES=(grafana prometheus loki alloy mlflow)
OBSERVABILITY_VOLUMES=(
  gentleman-stack_alloy_data
  gentleman-stack_grafana_data
  gentleman-stack_prometheus_data
  gentleman-stack_loki_data
  gentleman-stack_mlflow_data
)

case "${1:-}" in
  "")
    ;;
  --restart)
    RESTART_STACK="true"
    ;;
  -h|--help)
    cat <<'EOF'
Usage: ./observability/reset-data.sh [--restart]

Stops the local observability stack and removes its named Docker volumes.

Options:
  --restart    Start the stack again after removing persisted data.
  -h, --help   Show this help message.
EOF
    exit 0
    ;;
  *)
    printf 'Unsupported argument: %s\n' "$1" >&2
    exit 1
    ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  printf 'docker is required to reset the observability stack.\n' >&2
  exit 1
fi

cd "${REPO_ROOT}"

printf 'Stopping observability services managed by the root compose file...\n'
docker compose -f docker-compose.yml stop "${OBSERVABILITY_SERVICES[@]}" >/dev/null 2>&1 || true
docker compose -f docker-compose.yml rm -f -s -v "${OBSERVABILITY_SERVICES[@]}" >/dev/null 2>&1 || true

printf 'Removing observability named volumes...\n'
for volume_name in "${OBSERVABILITY_VOLUMES[@]}"; do
  docker volume rm "${volume_name}" >/dev/null 2>&1 || true
done

if [ "${RESTART_STACK}" = "true" ]; then
  printf 'Restarting observability services...\n'
  docker compose -f docker-compose.yml up -d "${OBSERVABILITY_SERVICES[@]}"
fi

printf 'Observability data reset complete.\n'