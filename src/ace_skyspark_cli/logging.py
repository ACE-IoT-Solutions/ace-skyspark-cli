"""Logging configuration for ACE SkySpark CLI.

Provides structured logging using structlog with both console and JSON output support.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import FilteringBoundLogger, Processor


def configure_logging(log_level: str = "INFO", json_format: bool = False) -> None:
    """Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON output format instead of console format
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper())

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )

    # Shared processors for both JSON and console
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    # Choose renderer based on format
    if json_format:
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.RichTracebackFormatter(),
            ),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> FilteringBoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (defaults to caller's module name)

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


def log_config(config: dict[str, Any]) -> None:
    """Log configuration at startup (with sensitive data masked).

    Args:
        config: Configuration dictionary to log
    """
    logger = get_logger(__name__)
    logger.info("application_config", config=config)
