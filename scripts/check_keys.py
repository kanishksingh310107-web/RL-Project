"""Check status of required and optional API keys.

Prints ONLY 'set' or 'not set' for each key.
NEVER prints or logs key values.
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.core.config import get_setting

KEYS_TO_CHECK = [
    ("GEOAPIFY_API_KEY", "Required for live places, geocoding & accommodation"),
    ("GOOGLE_CLIENT_ID", "Optional for Google sign-in"),
    ("AUTH_SECRET_KEY", "Optional auth session secret"),
]

def main() -> int:
    print("=== API Key Status Check ===")
    all_required_set = True
    for key, desc in KEYS_TO_CHECK:
        val = get_setting(key, "").strip()
        status = "set" if val else "not set"
        print(f"{key:20} : {status} ({desc})")
        if key == "GEOAPIFY_API_KEY" and not val:
            all_required_set = False
    print("============================")
    return 0 if all_required_set else 1

if __name__ == "__main__":
    sys.exit(main())
