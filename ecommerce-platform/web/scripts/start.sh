#!/bin/sh
set -eu

root_env_file="${ROOT_ENV_FILE:-/workspace/root.env}"
wait_seconds="${WEB_ENV_WAIT_SECONDS:-300}"
interval=2
elapsed=0

read_publishable_key() {
  if [ ! -f "$root_env_file" ]; then
    return 1
  fi

  value=$(grep '^NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY=' "$root_env_file" | tail -n 1 | cut -d '=' -f 2- || true)
  value=$(printf '%s' "$value" | tr -d '\r')
  value=$(printf '%s' "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

  if [ -z "$value" ]; then
    return 1
  fi

  printf '%s' "$value"
}

publishable_key="${NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY:-}"

while [ -z "$publishable_key" ]; do
  publishable_key=$(read_publishable_key || true)

  if [ -n "$publishable_key" ]; then
    break
  fi

  if [ "$elapsed" -ge "$wait_seconds" ]; then
    echo "Timed out waiting for NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY in $root_env_file." >&2
    exit 1
  fi

  sleep "$interval"
  elapsed=$((elapsed + interval))
done

export NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY="$publishable_key"

if [ ! -f .next/BUILD_ID ]; then
  echo "Building storefront with resolved Medusa publishable key."
  yarn build
fi

exec yarn start