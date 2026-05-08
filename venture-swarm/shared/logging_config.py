from __future__ import annotations

import logging

from rich.logging import RichHandler


def setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=log_level.upper(),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True, show_path=False)],
        force=True,
    )


def get_logger(component: str) -> logging.Logger:
    return logging.getLogger(component)
