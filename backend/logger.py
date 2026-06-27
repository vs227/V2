import logging
import os
from datetime import datetime
from config import get_settings

_loggers: dict[str, logging.Logger] = {}


def setup_logger(name: str) -> logging.Logger:
    if name in _loggers:
        return _loggers[name]

    settings = get_settings()
    os.makedirs(settings.log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level.upper()))

    if logger.handlers:
        _loggers[name] = logger
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    import sys
    if sys.platform == "win32":
        try:
            # Safely reconfigure encoding without detaching the underlying buffer
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    log_file = os.path.join(settings.log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    _loggers[name] = logger
    return logger
