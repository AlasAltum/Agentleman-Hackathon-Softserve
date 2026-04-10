# Quick Start Guide

Get the **SRE Incident Intake & Triage Agent** running locally in 5 minutes—a full-stack platform with an e-commerce storefront and observability stack.

## Prerequisites

- **Docker & Docker Compose** (version 20.10+)
- **Git**
- **API Key** for at least one LLM provider (see options below)

> **No local setup needed!** All services run in Docker containers.

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/softserve/Agentleman-Hackathon-Softserve.git
cd Agentleman-Hackathon-Softserve
```

---

## Step 2: Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Open `.env` and fill in the **required** API keys below:

### Essential Configuration

#### LLM Provider (Choose One)

Choose your preferred LLM provider and API key:

**Google Gemini (Default - Recommended)**
```env
LLM_PROVIDER=google
LLM_MODEL=gemini-2.5-flash
GOOGLE_API_KEY=your_google_api_key_here
EMBED_PROVIDER=google
EMBED_MODEL=gemini-embedding-2-preview
```


**Local Ollama (Free - Requires Ollama Installation)**
```env
LLM_PROVIDER=ollama
LLM_MODEL=llama2
LLM_BASE_URL=http://host.docker.internal:11434
EMBED_PROVIDER=local
EMBED_MODEL=nomic-embed-text
```

#### Optional: Jira/Confluence Integration
```env
ATLASSIAN_EMAIL=your_jira_email@example.com
ATLASSIAN_API_TOKEN=your_jira_api_token
JIRA_BASE_URL=https://your-domain.atlassian.net
```

#### Optional: Nylas Email Notifications
```env
NYLAS_API_KEY=your_nylas_api_key
NYLAS_GRANT_ID=your_nylas_grant_id
NYLAS_EMAIL_ADDRESS=alerts@example.com
NYLAS_TEAM_EMAIL_RECIPIENTS=sre-team@example.com
```

> ℹ️ Other settings have sensible defaults and can be left as-is for local development.

---

## Step 3: Start the Stack

Build and start all services:

```bash
docker compose up --build
```

**What's starting:**
- **Backend API** (SRE Workflow Agent) → http://localhost:8000
- **PostgreSQL Database** → localhost:5432
- **Qdrant Vector DB** → localhost:6333
- **E-commerce API** (Medusa) → http://localhost:9000
- **Storefront** (Next.js) → http://localhost:8001
- **Grafana Dashboards** → http://localhost:3000 (admin/admin)
- **Prometheus Metrics** → http://localhost:9090
- **Loki Log Aggregation** → http://localhost:3100
- **MLflow Usage Traces** → http://localhost:5001

Wait for all services to be healthy (typically 30-60 seconds).

---

## Step 4: Verify the Installation

### Health Check

Check API health:
```bash
curl http://localhost:8000/health
```

### Quick Test: SRE Agent

Ingest an incident via the backend API:
```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Database Connection Timeout",
    "description": "Production database experiencing connection timeouts",
    "severity": "high"
  }'
```

### E-commerce Storefront

Visit http://localhost:8001 to see the storefront (initially empty until seeded).

### Observability Dashboard

Access Grafana at http://localhost:3000:
- **Username:** admin
- **Password:** admin

---

## Step 5: Run Tests

### Backend Unit & Integration Tests

```bash
docker compose exec hackaton-backend pytest tests/ -v
```

### Specific Test Suite

```bash
# Test workflow
docker compose exec hackaton-backend pytest tests/test_sre_workflow.py -v

# Test integrations
docker compose exec hackaton-backend pytest tests/test_ingest_integration.py -v
```

---

## Common Tasks

### Stop All Services

```bash
docker compose down
```

### Stop and Clear Data

```bash
docker compose down -v
```

### View Logs

**All services:**
```bash
docker compose logs -f
```

**Specific service:**
```bash
docker compose logs -f hackaton-backend
```

### Access Database

```bash
docker compose exec db psql -U postgres -d postgres
```

### Rebuild a Specific Service

```bash
docker compose up --build hackaton-backend
```

---

## Troubleshooting

### "Cannot connect to Docker daemon"
Ensure Docker is running:
```bash
docker ps
```

### API returns 500 Error
Check logs:
```bash
docker compose logs hackaton-backend
```

### "Invalid API Key" Error
Verify your API key in `.env` matches your chosen LLM provider (Google, OpenRouter, etc.).

### Database Connection Errors
Ensure PostgreSQL is healthy:
```bash
docker compose logs db
```

### Qdrant Vector DB not Responding
Restart Qdrant:
```bash
docker compose restart hackaton-qdrant
```

---

## Next Steps

- **Explore SRE Features:** See [AGENTS_USE.md](AGENTS_USE.md) for agent capabilities
- **Understand Architecture:** See [README.md](README.md) for architecture overview
- **Scale in Production:** See [SCALING.md](SCALING.md) for deployment guidelines
- **API Documentation:** Check backend logs for OpenAPI docs at http://localhost:8000/docs

---

## Need Help?

- Check the main [README.md](README.md)
- Review [backend/README.md](backend/README.md)
- Check service logs: `docker compose logs SERVICE_NAME`
- Verify `.env` configuration matches your chosen LLM provider