#!/usr/bin/env python3
"""SMC Signal Bot — entry point.

Usage:
    python run.py

Opens the dashboard at http://localhost:8080
"""

import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path so `bot.*` and `smartmoneyconcepts` resolve.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from bot.ui.dashboard import start_dashboard  # noqa: E402

if __name__ == "__main__":
    start_dashboard()
