# SRE Platform

Incident intake platform for SRE engineers.

## Structure

```
sre-platform/
├── api/   FastAPI backend (Python, Poetry)
└── web/   React + TypeScript frontend (Vite)
```

## Running with Docker Compose

```bash
cd sre-platform
cp api/.env.example api/.env   # adjust values if needed
docker compose up --build
```

- Web UI: http://localhost:3000
- API:    http://localhost:8000

## Running locally (dev)

**API**
```bash
cd api
poetry install
poetry run uvicorn src.main:app --reload
```

**Web**
```bash
cd web
npm install
npm run dev
```

## Auth

Login accepts any username/password and returns a JWT. This is intentionally stubbed — real user storage will be added later.
