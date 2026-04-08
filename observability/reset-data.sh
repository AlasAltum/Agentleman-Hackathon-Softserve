#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RESTART_STACK="false"

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

printf 'Stopping observability stack and removing persisted volumes...\n'
docker compose \
  -f docker-compose.yml \
  -f observability/docker-compose.yml \
  down --volumes --remove-orphans

if [ "${RESTART_STACK}" = "true" ]; then
  printf 'Restarting observability stack...\n'
  docker compose \
    -f docker-compose.yml \
    -f observability/docker-compose.yml \
    up -d
fi

printf 'Observability data reset complete.\n'