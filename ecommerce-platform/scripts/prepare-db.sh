#!/bin/sh
set -eu

export PGPASSWORD="${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

db_name="${ECOMMERCE_DB_NAME:?ECOMMERCE_DB_NAME is required}"
port="${POSTGRES_PORT:-5432}"

if psql -h db -U "${POSTGRES_USER:?POSTGRES_USER is required}" -p "$port" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$db_name'" | grep -q 1; then
  echo "Database '$db_name' already exists."
  exit 0
fi

echo "Creating database '$db_name'."
psql -h db -U "$POSTGRES_USER" -p "$port" -d postgres -c "CREATE DATABASE \"$db_name\""