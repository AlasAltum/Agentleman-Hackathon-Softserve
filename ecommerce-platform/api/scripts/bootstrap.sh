#!/bin/sh
set -eu

echo "Running Medusa database migrations."
npx medusa db:migrate

echo "Running ecommerce bootstrap script."
npx medusa exec ./src/scripts/bootstrap.ts

if [ "${ECOMMERCE_CREATE_ADMIN_USER:-false}" = "true" ]; then
  echo "Creating Medusa admin user."
  ./scripts/create-admin-user.sh
fi

echo "Exporting Medusa publishable key."
npx medusa exec ./src/scripts/export-publishable-key.ts