"""
Shared logging bootstrap for the pipeline.

Usage
-----
    from auto_shorts_generator.logger import get_logger
    log = get_logger(__name__)
"""

import logging
from auto_shorts_generator import config


def get_logger(name: str) -> logging.Logger:
    """Return a consistently-formatted logger bound to *name*."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(config.LOG_FORMAT))
        logger.addHandler(handler)
    logger.setLevel(config.LOG_LEVEL)
    return logger
