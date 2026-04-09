# Ecommerce Dockerization Plan

## Goal

Dockerize the Medusa ecommerce stack so it can be started from the repository root alongside the existing backend and observability stacks, while reusing the existing Postgres service from `backend/docker-compose.yml`.

The required bootstrap order is:

1. Start the shared Postgres service.
2. Create a dedicated Medusa logical database inside the shared Postgres instance if it does not already exist.
3. Initialize `ecommerce-platform/api` with:
	 - `npx medusa db:migrate`
	 - `yarn run seed`
4. Extract the Medusa publishable API key and persist it to the root `.env` as `NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY`.
5. Start `ecommerce-platform/web` only after that key exists.

Admin user creation is optional and should be treated as a separate Medusa Admin access step, not a requirement for storefront bootstrap.

## What Is Already True In This Repo

- The root `docker-compose.yml` already includes `backend/docker-compose.yml` and `observability/docker-compose.yml`.
- The backend stack already owns the shared Postgres service named `db`.
- `ecommerce-platform/api/medusa-config.ts` reads `DATABASE_URL`, `STORE_CORS`, `ADMIN_CORS`, `AUTH_CORS`, `JWT_SECRET`, and `COOKIE_SECRET` from the environment.
- `ecommerce-platform/web/next.config.js` fails fast if `NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY` is missing.
- `ecommerce-platform/web/src/middleware.ts` also reads `MEDUSA_BACKEND_URL` and `NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY` at startup.
- `ecommerce-platform/api/src/scripts/seed.ts` already creates a publishable API key and links it to the default sales channel.

## Important Findings

### 1. The publishable key is not tied to the admin user

The admin user is useful for logging into Medusa Admin, but the publishable storefront key is a separate Medusa resource. The key should be exported from Medusa's API key records, not derived from the admin user's credentials.

That matters because the current seed script already creates the publishable key. The cleanest plan is to export that existing key after seeding instead of creating a second key through the admin UI or through a login flow.

As a result, creating an admin user is not required for the ecommerce storefront to work. Keep that step only if you also want access to the Medusa Admin UI.

### 2. Reusing the same Postgres service still allows a dedicated logical database

In this repository, the selected approach is:

1. Reuse the same Postgres container from the backend stack.
2. Create a separate logical database for Medusa, for example `medusa`.

`npx medusa db:migrate` is not the database-creation step. It runs Medusa's migrations against the database already referenced by `DATABASE_URL`, which means the target database should exist before that command runs.

This is the preferred operational choice because it keeps the backend application and Medusa isolated at the database level while still reusing the same Postgres service.

### 3. Docker Compose does not refresh `.env` during the same `up`

If an init container writes `NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY` into the root `.env` during `docker compose up`, sibling services do not automatically re-read that file. Compose resolves `.env` before containers start.

This is the main orchestration constraint for the storefront.

### 4. The web app needs the key before it can build or start

The storefront validates `NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY` in `next.config.js`. Because of that, the key must exist before the web build or startup command runs.

## Recommended Proposal

### Proposal A: Two-phase bootstrap using one-shot init containers

This is the recommended approach because it is the most reliable with Docker Compose, the root `.env`, and Next.js public environment variables.

#### Why this is the safest option

- It keeps the root `.env` as the centralized source of truth.
- It avoids trying to make Docker Compose reload environment variables mid-run.
- It avoids starting the Next.js storefront before the publishable key exists.
- It avoids coupling key extraction to an admin login flow.

#### Planned orchestration

1. Add `ecommerce-platform/docker-compose.yml`.
2. Include it from the root `docker-compose.yml`.
3. Add a healthcheck to the backend `db` service so ecommerce services can depend on database readiness, not just container startup.
4. Add a one-shot `ecommerce-db-prepare` service that connects to `db` and runs `CREATE DATABASE medusa` only if that database does not already exist.
5. Add a one-shot `ecommerce-api-init` service that runs the Medusa bootstrap commands.
6. Make `ecommerce-api-init` write the publishable key into the root `.env`.
7. Start `ecommerce-api` only after `ecommerce-api-init` completes successfully.
8. Run a second `docker compose up` for `ecommerce-api` and `ecommerce-web` so the web container sees the newly written root `.env` value from the beginning.

#### Expected service flow

`db` -> `ecommerce-db-prepare` -> `ecommerce-api-init` -> `ecommerce-api` -> `ecommerce-web`

#### What `ecommerce-api-init` should do

The init service should execute the following steps in order:

```sh
npx medusa db:migrate
yarn run seed
npx medusa exec ./src/scripts/export-publishable-key.ts
```

If Medusa Admin access is also required, an optional admin bootstrap step can run after migrations and seed:

```sh
npx medusa user -e ${ECOMMERCE_ADMIN_EMAIL} -p ${ECOMMERCE_ADMIN_PASSWORD}
```

#### Optional implementation detail

`npx medusa user ...` should be wrapped in an idempotent script. If the admin user already exists, the init service should treat that as success and continue. It should not hide unrelated failures.

#### How the publishable key should be exported

Add a dedicated Medusa script such as `src/scripts/export-publishable-key.ts` that:

1. Queries the publishable API key record from Medusa.
2. Reads the full `token` value.
3. Upserts `NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY=pk_...` into the root `.env`.
4. Optionally also upserts `MEDUSA_BACKEND_URL=http://ecommerce-api:9000` if that value is not already centralized.

This is preferable to a raw SQL query because it stays inside Medusa's own application layer.

#### Root command shape

The root workflow can later be exposed as either a helper script or documented as two commands:

```sh
docker compose run --rm ecommerce-api-init
docker compose up -d ecommerce-api ecommerce-web
```

That still keeps everything under Docker Compose, but it respects how Compose and Next.js actually handle environment variables.

## Alternative Proposal

### Proposal B: Single `docker compose up` with a generated runtime env file

This option is possible, but it is more complex.

#### How it would work

1. `ecommerce-api-init` would still run migrations, seed, admin creation, and key export.
2. In addition to updating the root `.env`, it would write a shared runtime file such as `/shared/ecommerce.runtime.env` on a bind mount or named volume.
3. `ecommerce-web` would wait for that file, source it in its entrypoint, and only then run `yarn build` followed by `yarn start`.

#### Why this is more complex

- The storefront image can no longer assume the key exists at image build time.
- The container entrypoint must handle waiting, env loading, build, and startup.
- Startup becomes slower because the Next.js build happens after the API init job, not during image build.

#### When to choose this option

Choose this only if a single `docker compose up` command is a hard requirement.

## Less Recommended Proposal

### Proposal C: Extract the key through the Medusa Admin API

This would create the admin user, log in through the Admin API, and then call the API key endpoints to create or fetch a publishable key.

It is valid, but it is not the cleanest solution for this repo because:

- the seed script already creates a publishable key,
- it adds an unnecessary authentication round trip,
- it introduces more moving parts than querying Medusa internally after seed.

Use this only if you explicitly want the key lifecycle to be managed through the Admin API instead of the existing seed flow.

## Changes That Will Be Needed

### Root compose

Extend the root `docker-compose.yml` include list with the ecommerce stack:

```yml
include:
	- path: backend/docker-compose.yml
		project_directory: backend
	- path: observability/docker-compose.yml
		project_directory: observability
	- path: ecommerce-platform/docker-compose.yml
		project_directory: ecommerce-platform
```

### Backend compose

Update `backend/docker-compose.yml` so the `db` service has a proper Postgres healthcheck. Without that, the ecommerce init job may start before Postgres is actually ready.

Optional but strongly recommended: add a named volume to the Postgres service so database state survives restarts.

### New ecommerce compose

Create `ecommerce-platform/docker-compose.yml` with at least these services:

- `ecommerce-db-prepare`
- `ecommerce-api-init`
- `ecommerce-api`
- `ecommerce-web`

### New Dockerfiles and helper scripts

Create the following files as part of the eventual implementation:

- `ecommerce-platform/api/Dockerfile`
- `ecommerce-platform/web/Dockerfile`
- `ecommerce-platform/api/src/scripts/export-publishable-key.ts`
- `ecommerce-platform/api/scripts/bootstrap.sh` or equivalent init wrapper
- `ecommerce-platform/web/scripts/start-with-env.sh` only if Proposal B is chosen

If Medusa Admin access is needed, also add an idempotent helper such as `ecommerce-platform/api/scripts/create-admin-user.sh`.

## Root `.env` Variables To Centralize

These values should live in the repository root `.env` or `.env.example` once implemented.

### Static values

```env
ECOMMERCE_DB_NAME=medusa
ECOMMERCE_API_PORT=9000
ECOMMERCE_WEB_PORT=8001
ECOMMERCE_STORE_CORS=http://localhost:8001
ECOMMERCE_ADMIN_CORS=http://localhost:9000
ECOMMERCE_AUTH_CORS=http://localhost:9000,http://localhost:8001
MEDUSA_BACKEND_URL=http://ecommerce-api:9000
NEXT_PUBLIC_BASE_URL=http://localhost:8001
```

If Medusa Admin access is also required, centralize these optional values too:

```env
ECOMMERCE_ADMIN_EMAIL=test-admin@gmail.com
ECOMMERCE_ADMIN_PASSWORD=admin
```

### Derived value

```env
ECOMMERCE_DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:${POSTGRES_PORT}/${ECOMMERCE_DB_NAME}
```

### Generated value

```env
NEXT_PUBLIC_MEDUSA_PUBLISHABLE_KEY=pk_...
```

## Final Recommendation

Implement Proposal A first.

Use the dedicated-database variant of Proposal A: share the backend Postgres service, but create and use a separate `medusa` database for the ecommerce API.

The admin-user creation step should stay optional because it is not required for exporting the publishable storefront key.

If later you want a single-command experience, keep the same init logic and move to Proposal B by adding a shared runtime env file and a smarter web entrypoint.
