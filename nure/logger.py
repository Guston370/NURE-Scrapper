"""
NURE Dataset Generator - Logging Setup
=========================================
Centralized loguru-based logger with file rotation.
"""

import sys
from pathlib import Path
from loguru import logger

from nure.config import LOGS_DIR, LOG_LEVEL, LOG_ROTATION


def setup_logger(name: str = "nure") -> "logger":
    """Configure and return the application logger."""
    logger.remove()

    # Console handler - colored, concise
    logger.add(
        sys.stdout,
        level=LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File handler - full detail, rotated
    log_file = LOGS_DIR / f"{name}.log"
    logger.add(
        str(log_file),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=LOG_ROTATION,
        retention="30 days",
        compression="gz",
        encoding="utf-8",
    )

    # Separate error log
    error_file = LOGS_DIR / f"{name}_errors.log"
    logger.add(
        str(error_file),
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}\n{exception}",
        rotation=LOG_ROTATION,
        retention="30 days",
        encoding="utf-8",
    )

    return logger


# Module-level default logger
setup_logger()
