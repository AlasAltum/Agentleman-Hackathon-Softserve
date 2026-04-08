import logging
import os

_APP_ENV = os.getenv("APP_ENV", "prod").lower()
_LEVEL = logging.INFO if _APP_ENV == "dev" else logging.WARNING

logging.basicConfig(
    level=_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%d-%m-%Y %H:%M:%S",
)

logger = logging.getLogger("estampapro")
logger.setLevel(_LEVEL)