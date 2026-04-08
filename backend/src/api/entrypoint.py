from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.src.api.routes.example_routes import router as example_router
import os

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app = FastAPI(
    title="Llama Index API",
    description="API backend",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(example_router) 

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
