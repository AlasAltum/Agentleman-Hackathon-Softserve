#!/usr/bin/env python3
"""
Ejecuta el SREIncidentWorkflow completo end-to-end con datos de incidente realistas
llamando al endpoint POST /api/ingest del servidor.

Carga automáticamente las variables de entorno desde backend/.env
(incluyendo GOOGLE_API_KEY para Gemini y el resto de la configuración).

Uso:
    cd backend
    poetry run python scripts/run_workflow_mock.py

    # Cambiar escenario:
    SCENARIO=infra      poetry run python scripts/run_workflow_mock.py
    SCENARIO=codebase   poetry run python scripts/run_workflow_mock.py
    SCENARIO=telemetry  poetry run python scripts/run_workflow_mock.py
    SCENARIO=alert_storm    poetry run python scripts/run_workflow_mock.py
    SCENARIO=regression poetry run python scripts/run_workflow_mock.py
    SCENARIO=all        poetry run python scripts/run_workflow_mock.py

    # Cambiar URL del servidor:
    API_BASE_URL=http://localhost:8000  poetry run python scripts/run_workflow_mock.py

Escenarios:
    default      → HTTP 500 en checkout (new_incident)
    infra        → Pod crashloop + Terraform drift (new_incident + infra_analyzer)
    codebase     → NullPointerException con stacktrace (new_incident + codebase_analyzer)
    telemetry    → CPU spike + p99 latency (new_incident + telemetry_analyzer)
    alert_storm  → Alerta repetida de DB pool exhausted (ALERT_STORM)
    regression   → JWT 401 ya visto hace meses (HISTORICAL_REGRESSION)
"""

import asyncio
import os
import sys
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# ── Cargar .env desde backend/.env (si existe) ────────────────────────────────
env_file = backend_dir / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file, override=False)
    print(f"[env] Cargado desde {env_file}")
else:
    print(f"[env] No se encontró {env_file} — usando variables de entorno del sistema")


# ── Escenarios realistas ───────────────────────────────────────────────────────

SCENARIOS: dict[str, dict] = {
    "default": {
        "description": "HTTP 500 en checkout → new_incident",
        "incident": {
            "text_desc": (
                "Users are getting intermittent HTTP 500 errors on the /checkout endpoint. "
                "Issue started approximately 20 minutes ago. ~15% of checkout requests are failing. "
                "No recent deploys were made. Database latency looks normal in Datadog. "
                "Error message from logs: 'Internal Server Error — unable to serialize cart session'."
            ),
            "reporter_email": "alice.martin@ecommerce.com",
        },
    },
    "infra": {
        "description": "Pod crashloop + Terraform drift → new_incident + infra_analyzer",
        "incident": {
            "text_desc": (
                "Payments service pods are crashlooping after the Helm upgrade to v2.4.1. "
                "kubectl logs show: 'Error: kubernetes secret payments-db-creds not found in namespace payments'. "
                "Terraform plan is showing unexpected resource replacements in the VPC module. "
                "The deployment pipeline failed with: 'Error acquiring state lock — state file locked by another process'."
            ),
            "reporter_email": "devops-team@ecommerce.com",
            "file_content": b"""\
resource "aws_db_instance" "payments" {
  identifier        = "payments-prod"
  engine            = "postgres"
  engine_version    = "14.7"
  instance_class    = "db.t3.medium"
  allocated_storage = 100

  db_name  = "payments"
  username = "payments_user"
  password = var.db_password  # referenced but variable not defined in this workspace

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  skip_final_snapshot = false
  deletion_protection = true

  tags = {
    Environment = "production"
    Team        = "payments"
  }
}
""",
            "file_mime_type": "text/plain",
            "file_name": "payments_rds.tf",
        },
    },
    "codebase": {
        "description": "NullPointerException con stacktrace → new_incident + codebase_analyzer",
        "incident": {
            "text_desc": (
                "The payment processor is throwing an AttributeError after the last deploy (v3.12.0). "
                "Affects ~8% of transactions. The error occurs when processing 3D Secure callbacks. "
                "Stack trace and error log attached below."
            ),
            "reporter_email": "backend-squad@ecommerce.com",
            "file_content": b"""\
2026-04-08T14:32:11.842Z ERROR [payments.processor] Unhandled exception during payment processing
Traceback (most recent call last):
  File "/app/payments/views.py", line 89, in process_3ds_callback
    result = processor.finalize_charge(session_id, callback_data)
  File "/app/payments/processor.py", line 203, in finalize_charge
    return self._gateway_client.confirm(charge_id=session.charge_id, data=callback_data)
  File "/app/payments/gateway.py", line 114, in confirm
    return self._http.post(f"/charges/{charge_id}/confirm", json=data)
AttributeError: 'NoneType' object has no attribute 'post'

During handling of the above exception, another exception occurred:
  File "/app/payments/processor.py", line 210, in finalize_charge
    self._metrics.increment("payment.error", tags={"reason": "gateway_client_none"})
AttributeError: 'NoneType' object has no attribute 'increment'

Context: session_id=sess_8f3a2c, user_id=usr_00142, amount=129.99, currency=EUR
Gateway client initialization: client=None (last successful init: 2026-04-08T14:28:00Z)
Possible cause: gateway client not re-initialized after connection pool reset in v3.12.0
""",
            "file_mime_type": "text/plain",
            "file_name": "payment_error.log",
        },
    },
    "telemetry": {
        "description": "CPU spike + p99 latency → new_incident + telemetry_analyzer",
        "incident": {
            "text_desc": (
                "The api-gateway service is experiencing a severe performance degradation. "
                "CPU usage spiked from 40% to 95% at 14:10 UTC. "
                "p99 latency went from 45ms to 3200ms. Memory utilization at 91%. "
                "Timeout errors increased from 0.1% to 12% of requests. "
                "Alert triggered: 'SRE-ALERT: api-gateway p99 > 2000ms for 5 consecutive minutes'. "
                "No recent deploy. Upstream services (auth, catalog) look healthy."
            ),
            "reporter_email": "sre-oncall@ecommerce.com",
        },
    },
    "alert_storm": {
        "description": "Alerta repetida DB pool exhausted → ALERT_STORM",
        "incident": {
            "text_desc": (
                "Database connection pool exhausted on order-service. "
                "Same alert firing every 2 minutes for the last hour. "
                "Error: 'psycopg2.OperationalError: connection pool exhausted (max=20)'. "
                "Multiple pods reporting identical errors simultaneously. "
                "This is the 8th alert for the same issue in the past 90 minutes."
            ),
            "reporter_email": "oncall-sre@ecommerce.com",
        },
    },
    "regression": {
        "description": "JWT 401 ya visto hace meses → HISTORICAL_REGRESSION",
        "incident": {
            "text_desc": (
                "Auth service returning 401 Unauthorized for valid JWT tokens. "
                "Approximately 5% of authenticated requests are failing. "
                "Error message: 'JWT validation failed: token not yet valid (nbf claim in future)'. "
                "Issue started after the NTP config change on the auth service hosts. "
                "Users are getting logged out randomly."
            ),
            "reporter_email": "security-team@ecommerce.com",
        },
    },
}


# ── Runner ────────────────────────────────────────────────────────────────────

async def run_scenario(name: str, scenario: dict, base_url: str) -> dict:
    import httpx

    sep = "=" * 72
    print(f"\n{sep}")
    print(f"  ESCENARIO : {name.upper()}")
    print(f"  {scenario['description']}")
    print(sep)

    inc_data = scenario["incident"]
    file_content = inc_data.get("file_content")
    file_mime_type = inc_data.get("file_mime_type", "text/plain")
    file_name = inc_data.get("file_name", "attachment.txt")

    print("\n  [1/2] INPUT")
    print(f"    reporter : {inc_data['reporter_email']}")
    print(f"    text     : {inc_data['text_desc'][:100].strip()}...")
    if file_content is not None:
        print(f"    file     : {file_name} ({file_mime_type})")

    # Build multipart form data
    data = {
        "text_desc": inc_data["text_desc"],
        "reporter_email": inc_data["reporter_email"],
    }
    files = []
    if file_content is not None:
        files.append(("file_attachments", (file_name, file_content, file_mime_type)))

    url = f"{base_url}/api/ingest"
    print(f"\n  [2/2] POST {url}")

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(url, data=data, files=files if files else None)

    if response.status_code != 200:
        print(f"\n  ERROR {response.status_code}: {response.text}")
        return {"error": response.status_code, "detail": response.text}

    result = response.json()

    dash = "─" * 72
    print(f"\n{dash}")
    print("  RESPUESTA")
    print(f"    status     : {result.get('status')}")
    print(f"    ticket_id  : {result.get('ticket_id')}")
    print(f"    ticket_url : {result.get('ticket_url')}")
    print(f"    action     : {result.get('action')}")
    print(f"    request_id : {result.get('request_id')}")
    print(dash)

    return result


async def main() -> None:
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
    scenario_name = os.getenv("SCENARIO", "default").lower()

    print(f"[config] API_BASE_URL = {base_url}")

    if scenario_name == "all":
        for name in SCENARIOS:
            await run_scenario(name, SCENARIOS[name], base_url)
    elif scenario_name in SCENARIOS:
        await run_scenario(scenario_name, SCENARIOS[scenario_name], base_url)
    else:
        print(f"Escenario desconocido: '{scenario_name}'")
        print(f"Disponibles: {', '.join(SCENARIOS.keys())}, all")
        sys.exit(1)

    print("\nDone.\n")


if __name__ == "__main__":
    asyncio.run(main())
