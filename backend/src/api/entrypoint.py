from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from src.api.routes.incident_routes import router as incident_router
from src.utils.logger import generate_request_id, bind_request_context, logger
from src.utils.setup import setup_defaults
from src.utils.tracing import configure_mlflow
import os
import time


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or generate_request_id()
        
        bind_request_context(request_id, path=request.url.path, method=request.method)
        
        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                latency_ms=latency_ms,
            )
            
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as e:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error_type=type(e).__name__,
                latency_ms=latency_ms,
                exc_info=True,
            )
            raise

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
]

configure_mlflow()
setup_defaults()

app = FastAPI(
    title="Llama Index API",
    description="API backend",
    version="1.0.0",
)

app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incident_router)

@app.get("/")
async def root():
    """Endpoint raíz de prueba"""
    return {"message": "Bienvenido a Llama Index Template API"}


@app.get("/health")
async def health_check():
    """Endpoint de salud de la API"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn

    app_env = os.getenv("APP_ENV", "prod").lower()
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8000"))

    if app_env == "dev":
        uvicorn.run(
            "api.entrypoint:app",
            host=host,
            port=port,
            reload=True,
            reload_dirs=[os.getenv("APP_RELOAD_DIR", "src")],
        )
    else:
        uvicorn.run("api.entrypoint:app", host=host, port=port)
