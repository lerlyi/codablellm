import logging
from typing import Final
from rich.logging import RichHandler

PACKAGE_LOGGER_NAME: Final[str] = __package__ or "codablellm"


def setup_logger(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    logger.setLevel(level)

    if not logger.handlers:
        rich_handler = RichHandler(
            show_time=True, show_level=True, show_path=False, rich_tracebacks=True
        )
        formatter = logging.Formatter("%(name)s - %(message)s")
        rich_handler.setFormatter(formatter)
        logger.addHandler(rich_handler)
        logger.propagate = False
    else:
        # Update all existing handler levels
        for handler in logger.handlers:
            handler.setLevel(level)
    return logger
