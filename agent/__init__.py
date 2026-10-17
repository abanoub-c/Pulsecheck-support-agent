"""Agent package; load shared project settings before agent modules initialize."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_env import load_project_env  # noqa: E402

load_project_env()
