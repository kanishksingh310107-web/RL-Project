"""Application configuration and environment variable loader.

Reads OS environment variables first, then falls back to parsing
the local .env file using a tiny manual parser (no external dependency).
"""
import os
from pathlib import Path
from typing import Optional, Dict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT_DIR / ".env"


def parse_dotenv(path: Path) -> Dict[str, str]:
    """Tiny manual .env file parser.
    
    Reads KEY=VALUE lines, ignoring blank lines and comments (#).
    Strips surrounding single or double quotes from values.
    """
    env_vars: Dict[str, str] = {}
    if not path.is_file():
        return env_vars
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                if key:
                    env_vars[key] = val
    except Exception:
        pass
    return env_vars


# Load from file if not already set in os.environ
_DOTENV = parse_dotenv(ENV_PATH)


def get_setting(key: str, default: str = "") -> str:
    """Retrieve setting from os.environ first, then .env, then default."""
    if key in os.environ:
        return os.environ[key]
    return _DOTENV.get(key, default)


GEOAPIFY_API_KEY: str = get_setting("GEOAPIFY_API_KEY", "")
GOOGLE_CLIENT_ID: str = get_setting("GOOGLE_CLIENT_ID", "")
AUTH_SECRET_KEY: str = get_setting("AUTH_SECRET_KEY", "dev_secret_key_123")


def get_geoapify_key() -> Optional[str]:
    """Return the Geoapify API key or None if not set."""
    key = get_setting("GEOAPIFY_API_KEY", "").strip()
    return key if key else None


def is_geoapify_configured() -> bool:
    """Check if a non-empty Geoapify API key is configured."""
    return get_geoapify_key() is not None
