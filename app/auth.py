# Authentication handling for google, email, phone, and guest login
import os
import uuid
import secrets
import hashlib
import json
import base64
from typing import Optional, Dict, Any, Tuple
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from app.database import get_connection

SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "dev_secret_key_123")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

def set_google_client_id(client_id: str):
    global GOOGLE_CLIENT_ID
    GOOGLE_CLIENT_ID = client_id.strip()

def get_google_client_id() -> str:
    return GOOGLE_CLIENT_ID

def verify_google_credential(credential: str) -> Dict[str, Any]:
    """Verifies a Google ID token and returns authentication data.
    Uses the stable ``sub`` claim as the internal identifier.
    """
    try:
        if GOOGLE_CLIENT_ID:
            # Verify token with Google
            id_info = id_token.verify_oauth2_token(credential, google_requests.Request(), GOOGLE_CLIENT_ID)
        else:
            # Development fallback: decode JWT without verification
            parts = credential.split('.')
            if len(parts) >= 2:
                payload_b64 = parts[1]
                payload_b64 += '=' * ((4 - len(payload_b64) % 4) % 4)
                id_info = json.loads(base64.urlsafe_b64decode(payload_b64).decode('utf-8'))
            else:
                raise ValueError('Invalid token format.')
        sub = id_info.get('sub')
        email = id_info.get('email')
        if not sub:
            raise ValueError('Google token missing sub claim.')
        if not email:
            raise ValueError('Google token missing email claim.')
        name = id_info.get('name') or email.split('@')[0]
        picture = id_info.get('picture')
        # Authenticate or register using ``sub`` as stable identifier
        result = authenticate_or_register(
            provider='google',
            identifier=sub,
            display_name=name,
            avatar_url=picture,
        )
        return result
    except Exception as e:
        raise ValueError(f'Google sign in failed: {str(e)}')

# Password hashing with salt
def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    salted = f"{salt}${password}${SECRET_KEY}"
    pwd_hash = hashlib.sha256(salted.encode('utf-8')).hexdigest()
    return f"{salt}${pwd_hash}", salt

def verify_password(plain_password: str, stored_hash: str) -> bool:
    try:
        salt, _ = stored_hash.split('$', 1)
        expected_hash, _ = hash_password(plain_password, salt)
        return secrets.compare_digest(stored_hash, expected_hash)
    except Exception:
        return False

# Main login / signup function
def authenticate_or_register(
    provider: str,
    identifier: str,
    password: Optional[str] = None,
    display_name: Optional[str] = None,
    avatar_url: Optional[str] = None
) -> Dict[str, Any]:
    clean_identifier = identifier.strip().lower()
    with get_connection() as conn:
        cursor = conn.cursor()
        if provider == "google":
            cursor.execute(
                "SELECT * FROM users WHERE (auth_provider = ? AND google_sub = ?) OR identifier = ?",
                (provider, clean_identifier, clean_identifier)
            )
        else:
            cursor.execute("SELECT * FROM users WHERE identifier = ?", (clean_identifier,))
        existing_user = cursor.fetchone()
        if existing_user:
            if provider == "email":
                if not existing_user["password_hash"]:
                    new_hash, _ = hash_password(password)
                    cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, existing_user["id"]))
                    conn.commit()
                elif not password or not verify_password(password, existing_user["password_hash"]):
                    raise ValueError("Invalid email or password.")
            user_id = existing_user["id"]
            user_name = existing_user["display_name"]
            user_avatar = existing_user["avatar_url"]
        else:
            user_id = str(uuid.uuid4())
            pwd_hash = None
            if provider == "email":
                if not password or len(password) < 6:
                    raise ValueError("Password must be at least 6 characters.")
                pwd_hash, _ = hash_password(password)
            if not display_name:
                if provider == "phone":
                    display_name = f"User ({clean_identifier[-4:]})"
                elif provider == "email":
                    display_name = clean_identifier.split("@")[0].title()
                else:
                    display_name = "Traveler"
            columns = ["id", "auth_provider", "identifier", "password_hash", "display_name", "avatar_url"]
            values = [user_id, provider, clean_identifier, pwd_hash, display_name, avatar_url]
            if provider == "google":
                columns.append("google_sub")
                values.append(clean_identifier)
            placeholders = ", ".join(["?" for _ in columns])
            cursor.execute(
                f"INSERT INTO users ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values)
            )
            conn.commit()
            user_name = display_name
            user_avatar = avatar_url
        cursor.execute("SELECT 1 FROM traveller_profiles WHERE user_id = ?", (user_id,))
        has_profile = cursor.fetchone() is not None
        token = f"tk_{user_id}_{secrets.token_hex(16)}"
        return {
            "user_id": user_id,
            "auth_provider": provider,
            "identifier": clean_identifier,
            "display_name": user_name,
            "avatar_url": user_avatar,
            "has_profile": has_profile,
            "token": token
        }

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, auth_provider, identifier, display_name, avatar_url FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
