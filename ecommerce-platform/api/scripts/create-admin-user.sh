#!/bin/sh
set -eu

email="${ECOMMERCE_ADMIN_EMAIL:-}"
password="${ECOMMERCE_ADMIN_PASSWORD:-}"

if [ -z "$email" ] || [ -z "$password" ]; then
  echo "ECOMMERCE_ADMIN_EMAIL and ECOMMERCE_ADMIN_PASSWORD must be set when ECOMMERCE_CREATE_ADMIN_USER=true." >&2
  exit 1
fi

set +e
output=$(npx medusa user -e "$email" -p "$password" 2>&1)
status=$?
set -e

if [ "$status" -eq 0 ]; then
  echo "$output"
  exit 0
fi

case "$output" in
  *"already exists"*|*"User with email"*)
    echo "Medusa admin user already exists, continuing."
    exit 0
    ;;
esac

echo "$output" >&2
exit "$status"