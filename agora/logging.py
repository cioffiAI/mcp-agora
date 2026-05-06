import logging
import os
from pathlib import Path


def setup_logging(name: str = "agora") -> logging.Logger:
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        log_dir = Path.home() / ".agora" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "agora.log"
        handler = logging.FileHandler(str(log_file), encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
    return logger
