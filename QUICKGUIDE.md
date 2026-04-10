# Quick Start Guide

Get the **SRE Incident Intake & Triage Agent** running locally in 5 minutes—a full-stack platform with an e-commerce storefront and observability stack.

## Prerequisites

- **Docker & Docker Compose** (version 20.10+)
- **Git**
- **API Key** for Google AI. Set the Google API key as an environment variable.

> **No local setup needed!** All services run in Docker containers.

---

## Step 1: Clone the Repository

```bash
git clone git@github.com:AlasAltum/Agentleman-Hackathon-Softserve.git
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

These are the only values you **must** set — everything else has a working default:

```env
# Local PostgreSQL password (choose any password)
POSTGRES_PASSWORD=your_password_here

# Google AI Studio — https://aistudio.google.com/apikey
GOOGLE_API_KEY=your_google_api_key_here

# Atlassian — https://id.atlassian.com/manage-profile/security/api-tokens
ATLASSIAN_EMAIL=your_jira_email@example.com
ATLASSIAN_API_TOKEN=your_jira_api_token

# Nylas — https://www.nylas.com/ (API keys → your app → Grants)
NYLAS_API_KEY=your_nylas_api_key
NYLAS_GRANT_ID=your_nylas_grant_id
```

> ℹ️ All other settings (LLM model, Jira URL, email addresses, ports, etc.) have sensible defaults and can be left as-is for local development.

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
curl -X POST http://localhost:8000/api/ingest \
  -F "text_desc=The api-gateway service has been experiencing severe performance degradation since 14:10 UTC. CPU usage spiked from 40% to 95% and p99 latency jumped from 45ms to 3200ms. Memory utilization is at 91% and timeout errors have increased from 0.1% to 12% of all requests. No recent deploys were made. Upstream services (auth, catalog) appear healthy. Alert triggered: 'SRE-ALERT: api-gateway p99 > 2000ms for 5 consecutive minutes'. Checkout and payment flows are severely impacted." \
  -F "reporter_email=client@company.com"
```

### E-commerce Storefront

Visit http://localhost:8001 to see the storefront (initially empty until seeded).

### Observability Dashboard

Access Grafana at http://localhost:3000:
- **Username:** admin
- **Password:** admin

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

**Specific service:**
```bash
docker logs hackaton-backend
```

### Access Database

```bash
docker compose exec db psql -U postgres -d postgres
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
