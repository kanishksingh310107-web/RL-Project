# Authentication handling for google, email, phone, and guest login
import uuid
import secrets
import hashlib
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from app.database import get_connection
from app.core.config import get_setting

AUTH_SECRET_KEY = get_setting("AUTH_SECRET_KEY")
APP_ENV = get_setting("APP_ENV", "development").lower()
if not AUTH_SECRET_KEY:
    if APP_ENV == "production":
        raise RuntimeError("AUTH_SECRET_KEY must be set in production environment.")
    AUTH_SECRET_KEY = "dev_secret_key_123"

SECRET_KEY = AUTH_SECRET_KEY
GOOGLE_CLIENT_ID = get_setting("GOOGLE_CLIENT_ID")
PBKDF2_ITERATIONS = 100_000

def set_google_client_id(client_id: str):
    global GOOGLE_CLIENT_ID
    cleaned = client_id.strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.apps\.googleusercontent\.com',cleaned):
        raise ValueError('Enter a valid Google OAuth Web client ID.')
    with get_connection() as conn:
        conn.execute('INSERT INTO a_public_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     ('google_client_id',cleaned))
    GOOGLE_CLIENT_ID = cleaned

def get_google_client_id() -> str:
    configured = get_setting('GOOGLE_CLIENT_ID','').strip()
    if configured:
        return configured
    try:
        with get_connection() as conn:
            row = conn.execute('SELECT value FROM a_public_settings WHERE key=?',('google_client_id',)).fetchone()
        return row[0] if row else GOOGLE_CLIENT_ID
    except sqlite3.OperationalError:
        return GOOGLE_CLIENT_ID

def verify_google_credential(credential: str) -> Dict[str, Any]:
    """Verifies a Google ID token and returns authentication data.
    Uses the stable ``sub`` claim as the internal identifier.
    """
    try:
        client_id = get_google_client_id()
        if not client_id:
            raise ValueError('Google sign-in is not configured on this site. Use email sign-in instead.')
        id_info = id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)
        sub = id_info.get('sub')
        email = id_info.get('email')
        if not sub:
            raise ValueError('Google token missing sub claim.')
        if not email:
            raise ValueError('Google token missing email claim.')
        if id_info.get('email_verified') is not True:
            raise ValueError('Use a Google account with a verified email address.')
        name = id_info.get('name') or email.split('@')[0]
        picture = id_info.get('picture')
        # Authenticate or register using ``sub`` as stable identifier
        result = authenticate_or_register(
            provider='google',
            identifier=sub,
            email=email,
            display_name=name,
            avatar_url=picture,
        )
        return result
    except (ValueError,TypeError) as exc:
        raise ValueError('Google could not verify this sign-in. Please select your account again.') from exc

# Password hashing with PBKDF2-HMAC-SHA256 (100,000 rounds) and backward compatibility
def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS
    ).hex()
    stored_hash = f"pbkdf2:sha256:{PBKDF2_ITERATIONS}${salt}${derived}"
    return stored_hash, salt

def verify_password(plain_password: str, stored_hash: str) -> bool:
    try:
        if stored_hash.startswith("pbkdf2:sha256:"):
            _, salt, derived = stored_hash.split("$", 2)
            expected = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt.encode("utf-8"),
                PBKDF2_ITERATIONS
            ).hex()
            return secrets.compare_digest(derived, expected)
        else:
            # Backward-compatible legacy format: salt$sha256_hash
            salt, hash_val = stored_hash.split("$", 1)
            salted = f"{salt}${plain_password}${AUTH_SECRET_KEY}"
            expected_hash = hashlib.sha256(salted.encode("utf-8")).hexdigest()
            return secrets.compare_digest(hash_val, expected_hash)
    except Exception:
        return False

# Main login / signup function
def authenticate_or_register(
    provider: str,
    identifier: str,
    password: Optional[str] = None,
    display_name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    mode: Optional[str] = None,
    email: Optional[str] = None,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    clean_identifier = identifier.strip().casefold()
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
        except Exception:
            pass
        user_columns = {r[1] for r in cursor.execute("PRAGMA table_info(users)").fetchall()}
        if provider == "google":
            clauses = ["google_sub = ?", "(auth_provider='google' AND identifier = ?)"]
            params = [clean_identifier, clean_identifier]
            if "email_normalized" in user_columns and email:
                clauses.append("email_normalized = ?")
                params.append(email.strip().casefold())
            cursor.execute("SELECT * FROM users WHERE " + " OR ".join(clauses), tuple(params))
        else:
            if "identifier_normalized" in user_columns:
                cursor.execute("SELECT * FROM users WHERE identifier_normalized = ? OR lower(identifier) = ?", (clean_identifier, clean_identifier))
            else:
                cursor.execute("SELECT * FROM users WHERE lower(identifier) = ?", (clean_identifier,))
        existing_user = cursor.fetchone()
        if existing_user:
            if provider == "email":
                if not existing_user["password_hash"]:
                    raise ValueError("This email is linked to another sign-in method. Use that method to continue.")
                if mode == "signup":
                    raise ValueError("An account with this email already exists. Please sign in instead.")
                if not password or not verify_password(password, existing_user["password_hash"]):
                    raise ValueError("Invalid email or password.")
            elif provider == "google" and "google_sub" in existing_user.keys():
                if existing_user["google_sub"] and existing_user["google_sub"] != clean_identifier:
                    raise ValueError("This email is already linked to a different Google account.")
                cursor.execute("UPDATE users SET google_sub=? WHERE id=? AND (google_sub IS NULL OR google_sub='')", (clean_identifier, existing_user["id"]))
            user_id = existing_user["id"]
            user_name = existing_user["display_name"]
            user_avatar = existing_user["avatar_url"]
        else:
            if provider == "email" and mode == "login":
                raise ValueError("No account exists for this email. Create an account first.")
            user_id = str(uuid.uuid4())
            pwd_hash = None
            if provider == "email":
                if not password or len(password) < 8:
                    raise ValueError("Password must be at least 8 characters.")
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
            if "username" in user_columns and provider == "email":
                account_username = (username or clean_identifier.split("@")[0]).strip()
                columns.extend(["username", "username_normalized", "email", "email_normalized", "identifier_normalized"])
                values.extend([account_username, account_username.casefold(), clean_identifier, clean_identifier, clean_identifier])
            if provider == "google":
                if "google_sub" in user_columns:
                    columns.append("google_sub")
                    values.append(clean_identifier)
                if "email" in user_columns:
                    columns.append("email")
                    values.append((email or clean_identifier).casefold())
                if "email_normalized" in user_columns:
                    columns.append("email_normalized")
                    values.append((email or clean_identifier).casefold())
                if "identifier_normalized" in user_columns:
                    columns.append("identifier_normalized")
                    values.append(clean_identifier)
            elif provider == "guest":
                columns.append("identifier_normalized")
                values.append(clean_identifier)
            placeholders = ", ".join(["?" for _ in columns])
            cursor.execute(
                f"INSERT INTO users ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values)
            )
            user_name = display_name
            user_avatar = avatar_url
        cursor.execute("SELECT 1 FROM traveller_profiles WHERE user_id = ?", (user_id,))
        has_profile = cursor.fetchone() is not None
        if "user_profile" in {r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
            cursor.execute("INSERT OR IGNORE INTO user_profile(user_id) VALUES(?)", (user_id,))
        token = secrets.token_urlsafe(32)
        tables = {r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "auth_sessions" in tables:
            cursor.execute("DELETE FROM auth_sessions WHERE user_id=? AND expires_at<=?", (user_id, datetime.now(timezone.utc).isoformat()))
            cursor.execute("INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, (datetime.now(timezone.utc)+timedelta(days=30)).isoformat()))
        conn.commit()
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
