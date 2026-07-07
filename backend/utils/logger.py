import logging
import sys
from pathlib import Path

from backend.config import DATA_DIR

_LOG_DIR = DATA_DIR / "logs"
_LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("stocktracing")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = logging.FileHandler(str(_LOG_DIR / "stocktracing.log"), encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    logger.propagate = False
