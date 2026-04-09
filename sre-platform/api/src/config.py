import os

JWT_SECRET: str = os.getenv("JWT_SECRET", "supersecretkey")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
CORS_ORIGIN: str = os.getenv("CORS_ORIGIN", "http://localhost:5173")
