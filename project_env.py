"""Load the project's single root .env file without overriding host settings."""

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_project_env() -> None:
    """Load environment values for local development; platform values win."""
    load_dotenv(dotenv_path=ENV_FILE, override=False)
