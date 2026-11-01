"""Utility helpers: logging + performance metrics."""
from __future__ import annotations

import logging
import sys
from typing import Iterable, Sequence

import numpy as np


def get_logger(name: str = "grids") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
        )
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


log = get_logger()
