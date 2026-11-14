"""Account sessions, mandatory profile gate, and user-owned travel history."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from app.database import get_connection
from app.precision import check_basic_missing
from app.auth import authenticate_or_register

class AErrorRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                issue = exc.errors()[0] if exc.errors() else {}
                field = str(issue.get("loc", [""])[-1]) or None
                message = issue.get("msg", "Invalid input")
                if message.startswith("Value error, "):
                    message = message[13:]
                body = {"detail": message, "code": "INVALID_INPUT"}
                if field and field not in ("body", "query", "path"):
                    body["field"] = field
                return JSONResponse(body, status_code=422)
            except HTTPException as exc:
                body = exc.detail if isinstance(exc.detail, dict) else {"detail": str(exc.detail), "code": "REQUEST_ERROR"}
                return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

        return handle


router = APIRouter(route_class=AErrorRoute)
RATING_KEYS = ("scenery", "food", "safety", "value_for_money", "crowds", "accessibility", "stay_quality", "overall")
TRIP_TYPES = {"solo", "couple", "friends", "family"}


def _error(status: int, detail: str, code: str, field: Optional[str] = None):
    body = {"detail": detail, "code": code}
    if field:
        body["field"] = field
    raise HTTPException(status_code=status, detail=body)


class HistoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination: str = Field(min_length=1, max_length=120)
    city: Optional[str] = Field(default=None, max_length=120)
    visited_on: date
    trip_type: str
    ratings: dict[str, StrictInt]
    would_revisit: StrictBool
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("destination", "city", "notes", mode="before")
    @classmethod
    def trim_text(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            raise ValueError("Must be text")
        return value.strip()

    @field_validator("destination")
    @classmethod
    def meaningful_destination(cls, value):
        if not value or not re.search(r"[^\W_]", value, re.UNICODE):
            raise ValueError("Enter a valid destination")
        return value

    @field_validator("trip_type")
    @classmethod
    def valid_trip_type(cls, value):
        value = value.strip().lower()
        if value not in TRIP_TYPES:
            raise ValueError("Choose solo, couple, friends, or family")
        return value

    @field_validator("visited_on")
    @classmethod
    def not_future(cls, value):
        if value > date.today():
            raise ValueError("Visited date cannot be in the future")
        return value

    @model_validator(mode="after")
    def valid_ratings(self):
        if set(self.ratings) != set(RATING_KEYS):
            raise ValueError("Provide a 1–5 rating for every travel category")
        if any(v < 1 or v > 5 for v in self.ratings.values()):
            raise ValueError("Ratings must be whole numbers from 1 to 5")
        return self


class HistoryChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice: str

    @field_validator("choice")
    @classmethod
    def valid_choice(cls, value):
        if value not in ("none", "provided"):
            raise ValueError("Choose none or provided")
        return value


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    mode: str = "login"
    username: Optional[str] = Field(default=None, min_length=3, max_length=24)
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    confirm_password: Optional[str] = None

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().casefold()
        if "@" in value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        if "@" not in value and not re.fullmatch(r"[A-Za-z0-9_.-]{3,24}", value):
            raise ValueError("Enter your email or username")
        return value

    @field_validator("username")
    @classmethod
    def valid_username(cls, value):
        if value is not None:
            value = value.strip()
            if not re.fullmatch(r"[A-Za-z0-9_.-]{3,24}", value):
                raise ValueError("Use 3–24 letters, numbers, dots, underscores, or hyphens")
        return value

    @field_validator("display_name", mode="before")
    @classmethod
    def clean_display_name(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            raise ValueError("Enter a valid name")
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be blank")
        return value

    @model_validator(mode="after")
    def check_mode_and_password(self):
        if self.mode not in ("login", "signup"):
            raise ValueError("Choose sign in or create account")
        if self.mode == "signup":
            if "@" not in self.email:
                raise ValueError("Enter a valid email address")
            if len(self.password) < 10:
                raise ValueError("Password must be at least 10 characters")
            if not self.username:
                raise ValueError("Choose a username")
            if self.confirm_password != self.password:
                raise ValueError("Passwords do not match")
            if not (re.search(r"[A-Z]", self.password) and re.search(r"[a-z]", self.password) and re.search(r"\d", self.password)):
                raise ValueError("Use at least one uppercase letter, lowercase letter, and number")
        return self


class GuestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    guest_id: str = Field(min_length=20, max_length=80)

    @field_validator("guest_id")
    @classmethod
    def valid_guest_id(cls, value):
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", value):
            raise ValueError("A valid guest identity is required")
        return value


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        _error(403, "Sign in to continue", "AUTH_REQUIRED")
    token = authorization[7:].strip()
    with get_connection() as conn:
        row = conn.execute("""SELECT u.id,u.display_name,u.auth_provider,u.identifier
            FROM auth_sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>?""", (_token_hash(token), datetime.now(timezone.utc).isoformat())).fetchone()
    if not row:
        _error(403, "Your session has expired. Please sign in again.", "SESSION_EXPIRED")
    return dict(row)


def require_profile_complete(user: dict = Depends(current_user), request: Request = None) -> dict:
    requested_user_id = request.path_params.get("user_id") if request else None
    if requested_user_id and requested_user_id != user["id"]:
        _error(403, "You cannot plan trips for another account", "USER_MISMATCH", "user_id")
    with get_connection() as conn:
        complete = _refresh_complete(conn, user["id"])
    if not complete:
        _error(403, "Complete your personalization questionnaire first", "PROFILE_INCOMPLETE")
    return user


@router.post("/api/account/login")
@router.post("/api/account/register", status_code=201)
def account_auth(payload: AccountInput, request: Request):
    ip = request.client.host if request.client else "unknown"
    login_key = hashlib.sha256(payload.email.encode()).hexdigest()
    ip_key = hashlib.sha256(ip.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        auth_email = payload.email
        if payload.mode == "login" and "@" not in payload.email:
            identity = conn.execute("SELECT identifier,email FROM users WHERE username_normalized=?", (payload.email,)).fetchone()
            if identity:
                auth_email = identity["email"] or identity["identifier"]
        conflicted = conn.execute("SELECT 1 FROM auth_identity_conflicts WHERE conflict_type IN ('email','identifier') AND normalized_value=?", (auth_email,)).fetchone()
        if conflicted:
            _error(409, "This sign-in identity has conflicting older accounts. Contact support to resolve it.", "ACCOUNT_IDENTITY_CONFLICT", "email")
        if payload.mode == "signup" and payload.username:
            taken = conn.execute("SELECT 1 FROM users WHERE username_normalized=?", (payload.username.casefold(),)).fetchone()
            if taken:
                _error(409, "That username is already in use", "USERNAME_TAKEN", "username")
        attempt = conn.execute("SELECT failed_count,window_started_at,locked_until FROM auth_login_attempts WHERE login_key=? AND ip_key=?", (login_key,ip_key)).fetchone()
        if attempt and attempt["locked_until"] and attempt["locked_until"] > now.isoformat():
            _error(429, "Too many attempts. Please try again in 15 minutes.", "LOGIN_RATE_LIMIT")
    try:
        result = authenticate_or_register("email", auth_email, password=payload.password,
            display_name=payload.display_name or payload.username, username=payload.username, mode=payload.mode)
        with get_connection() as conn:
            conn.execute("DELETE FROM auth_login_attempts WHERE login_key=? AND ip_key=?", (login_key,ip_key))
        return result
    except ValueError as exc:
        duplicate = "already exists" in str(exc).lower() or "already linked" in str(exc).lower()
        if payload.mode == "signup" and duplicate:
            _error(409, str(exc), "ACCOUNT_EXISTS", "email")
        with get_connection() as conn:
            if attempt and (now - datetime.fromisoformat(attempt["window_started_at"])).total_seconds() < 900:
                count = int(attempt["failed_count"]) + 1
                started = attempt["window_started_at"]
            else:
                count, started = 1, now.isoformat()
            locked = (now + timedelta(minutes=15)).isoformat() if count >= 5 else None
            conn.execute("INSERT INTO auth_login_attempts(login_key,ip_key,failed_count,window_started_at,locked_until) VALUES(?,?,?,?,?) ON CONFLICT(login_key,ip_key) DO UPDATE SET failed_count=excluded.failed_count,window_started_at=excluded.window_started_at,locked_until=excluded.locked_until", (login_key,ip_key,count,started,locked))
        _error(401, "Invalid email or password", "INVALID_CREDENTIALS")
    except sqlite3.IntegrityError:
        _error(409, "That email or username is already in use", "ACCOUNT_EXISTS", "email")


@router.post("/api/account/guest")
def guest_auth(payload: GuestInput):
    guest_id = payload.guest_id
    try:
        return authenticate_or_register("guest", guest_id, display_name="Guest traveler", mode="login")
    except sqlite3.IntegrityError:
        # A concurrent first login may have won the unique identity insert; retry lookup.
        return authenticate_or_register("guest", guest_id, display_name="Guest traveler", mode="login")


def _refresh_complete(conn, user_id: str) -> bool:
    prof = conn.execute("SELECT * FROM traveller_profiles WHERE user_id=?", (user_id,)).fetchone()
    try:
        profile = dict(prof) if prof else {}
        if prof and prof["raw_answers_json"]:
            raw = json.loads(prof["raw_answers_json"])
            profile["raw_answers"] = raw
            profile.update({k: v for k, v in raw.items() if k not in profile})
        basic_ok = bool(prof) and not check_basic_missing(profile)
    except Exception:
        basic_ok = False
    choice = conn.execute("SELECT history_choice FROM user_profile WHERE user_id=?", (user_id,)).fetchone()
    history_choice = choice[0] if choice else None
    entries = conn.execute("SELECT COUNT(*) FROM travel_history WHERE user_id=? AND source='manual'", (user_id,)).fetchone()[0]
    done = basic_ok and (history_choice == "none" or (history_choice == "provided" and entries > 0))
    conn.execute("UPDATE user_profile SET profile_complete=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (int(done), user_id))
    return bool(done)


@router.get("/api/profile/status")
def profile_status(user: dict = Depends(current_user)):
    with get_connection() as conn:
        complete = _refresh_complete(conn, user["id"])
    return {"profile_complete": complete}


@router.post("/api/profile/history/choice")
def save_history_choice(payload: HistoryChoice, user: dict = Depends(current_user)):
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM travel_history WHERE user_id=? AND source='manual'", (user["id"],)).fetchone()[0]
        if payload.choice == "none" and count:
            _error(409, "Remove your saved trips before selecting no travel history", "HISTORY_CONFLICT", "choice")
        conn.execute("UPDATE user_profile SET history_choice=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (payload.choice, user["id"]))
        complete = _refresh_complete(conn, user["id"])
    return {"history_choice": payload.choice, "profile_complete": complete}


def _history_list(conn, user_id: str):
    rows = [dict(r) for r in conn.execute("SELECT * FROM travel_history WHERE user_id=? ORDER BY visited_on DESC, destination COLLATE NOCASE", (user_id,))]
    # Completed trip history is read-only and merged from C-owned tables when available.
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "post_trip_feedback" in tables:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(post_trip_feedback)")}
        if {"trip_id", "user_id", "ratings_json", "trip_type", "would_revisit"}.issubset(cols):
            trip_cols = {r[1] for r in conn.execute("PRAGMA table_info(trips)")} if "trips" in tables else set()
            destination_field = "destination_name" if "destination_name" in trip_cols else ("destination" if "destination" in trip_cols else None)
            destination_expr = f"t.{destination_field}" if destination_field else "f.trip_id"
            published = " AND f.submitted_at IS NOT NULL" if "submitted_at" in cols else ""
            for r in conn.execute(f"SELECT f.trip_id,f.ratings_json,f.trip_type,f.would_revisit,f.notes,{destination_expr} AS destination FROM post_trip_feedback f " + ("LEFT JOIN trips t ON t.id=f.trip_id " if destination_field else "") + "WHERE f.user_id=?" + published, (user_id,)):
                if not conn.execute("SELECT 1 FROM travel_history WHERE user_id=? AND trip_id=?", (user_id, r["trip_id"])).fetchone():
                    excluded = conn.execute("SELECT 1 FROM travel_history_exclusions WHERE user_id=? AND trip_id=?", (user_id, r["trip_id"])).fetchone()
                    if excluded:
                        continue
                    notes = [r["notes"]] if r["notes"] else []
                    merged_ratings_json = r["ratings_json"] or "{}"
                    if "activity_runs" in tables:
                        run_cols = {c[1] for c in conn.execute("PRAGMA table_info(activity_runs)")}
                        if {"trip_id", "notes"}.issubset(run_cols):
                            run_query = "SELECT notes" + (",ratings_json" if "ratings_json" in run_cols else "") + " FROM activity_runs WHERE trip_id=? AND notes IS NOT NULL"
                            for run in conn.execute(run_query, (r["trip_id"],)):
                                notes.append(run["notes"])
                                if "ratings_json" in run.keys() and run["ratings_json"]:
                                    try:
                                        activities = json.loads(run["ratings_json"])
                                        if isinstance(activities, dict):
                                            base_ratings = json.loads(merged_ratings_json)
                                            for key in RATING_KEYS:
                                                if key in activities and type(activities[key]) is int and 1 <= activities[key] <= 5:
                                                    base_ratings.setdefault(key, activities[key])
                                            merged_ratings_json = json.dumps(base_ratings)
                                    except (TypeError, json.JSONDecodeError):
                                        pass
                    rows.append({"id": f"trip_{r['trip_id']}", "user_id": user_id, "destination": r["destination"] or "Completed trip", "city": None, "visited_on": None, "trip_type": r["trip_type"], "ratings_json": merged_ratings_json, "would_revisit": r["would_revisit"], "notes": "\n".join(notes) or None, "source": "trip", "trip_id": r["trip_id"]})
    for row in rows:
        try:
            row["ratings"] = json.loads(row.pop("ratings_json", "{}") or "{}")
        except (TypeError, json.JSONDecodeError):
            row["ratings"] = {}
        revisit = row["would_revisit"]
        if isinstance(revisit, str):
            row["would_revisit"] = True if revisit.casefold() in ("yes", "true", "1") else (False if revisit.casefold() in ("no", "false", "0") else None)
        else:
            row["would_revisit"] = bool(revisit) if revisit is not None else None
    return rows


@router.get("/api/profile/history")
def get_history(user: dict = Depends(current_user)):
    with get_connection() as conn:
        choice = conn.execute("SELECT history_choice FROM user_profile WHERE user_id=?", (user["id"],)).fetchone()
        rows = _history_list(conn, user["id"])
    return {"history_choice": choice[0] if choice else None, "entries": rows}


@router.post("/api/profile/history", status_code=201)
def add_history(payload: HistoryInput, user: dict = Depends(current_user)):
    if not payload.visited_on or not payload.destination.strip():
        _error(422, "Complete all required travel history fields", "INVALID_HISTORY")
    history_id = secrets.token_urlsafe(16)
    with get_connection() as conn:
        try:
            conn.execute("""INSERT INTO travel_history(id,user_id,destination,city,visited_on,trip_type,ratings_json,would_revisit,notes,source)
                VALUES(?,?,?,?,?,?,?,?,?,'manual')""", (history_id,user["id"],payload.destination,payload.city or None,payload.visited_on.isoformat(),payload.trip_type,json.dumps(payload.ratings),int(payload.would_revisit),payload.notes or None))
        except sqlite3.IntegrityError:
            _error(409, "This destination and date are already in your history", "DUPLICATE_HISTORY", "visited_on")
        conn.execute("UPDATE user_profile SET history_choice='provided' WHERE user_id=?", (user["id"],))
        complete = _refresh_complete(conn, user["id"])
    return {"id": history_id, "profile_complete": complete}


@router.put("/api/profile/history/{history_id}")
def edit_history(history_id: str, payload: HistoryInput, user: dict = Depends(current_user)):
    with get_connection() as conn:
        try:
            cur = conn.execute("""UPDATE travel_history SET destination=?,city=?,visited_on=?,trip_type=?,ratings_json=?,would_revisit=?,notes=?
                WHERE id=? AND user_id=? AND source='manual'""", (payload.destination,payload.city or None,payload.visited_on.isoformat(),payload.trip_type,json.dumps(payload.ratings),int(payload.would_revisit),payload.notes or None,history_id,user["id"]))
        except sqlite3.IntegrityError:
            _error(409, "This destination and date are already in your history", "DUPLICATE_HISTORY", "visited_on")
        if not cur.rowcount:
            _error(404, "Travel history entry not found", "HISTORY_NOT_FOUND")
        complete = _refresh_complete(conn, user["id"])
    return {"updated": True, "profile_complete": complete}


@router.delete("/api/profile/history/{history_id}")
def delete_history(history_id: str, user: dict = Depends(current_user)):
    with get_connection() as conn:
        row = conn.execute("SELECT source,trip_id FROM travel_history WHERE id=? AND user_id=?", (history_id,user["id"])).fetchone()
        if row and row["source"] == "manual":
            conn.execute("DELETE FROM travel_history WHERE id=? AND user_id=?", (history_id,user["id"]))
        elif row and row["source"] == "trip" and row["trip_id"]:
            conn.execute("INSERT OR IGNORE INTO travel_history_exclusions(user_id,trip_id) VALUES(?,?)", (user["id"],row["trip_id"]))
        else:
            _error(404, "Travel history entry not found", "HISTORY_NOT_FOUND")
        complete = _refresh_complete(conn, user["id"])
    return {"removed": True, "profile_complete": complete}


@router.delete("/api/profile/revisit/{history_id}")
def remove_revisit(history_id: str, user: dict = Depends(current_user)):
    with get_connection() as conn:
        row = conn.execute("SELECT source,trip_id FROM travel_history WHERE id=? AND user_id=?", (history_id,user["id"])).fetchone()
        if row and row["source"] == "manual":
            conn.execute("UPDATE travel_history SET would_revisit=0 WHERE id=? AND user_id=?", (history_id,user["id"]))
        elif row and row["source"] == "trip" and row["trip_id"]:
            conn.execute("INSERT OR IGNORE INTO travel_history_exclusions(user_id,trip_id) VALUES(?,?)", (user["id"],row["trip_id"]))
        else:
            _error(404, "Revisit entry not found", "HISTORY_NOT_FOUND")
    return {"removed": True}


@router.post("/api/account/logout")
def logout(user: dict = Depends(current_user), authorization: Optional[str] = Header(default=None)):
    token = authorization[7:].strip()
    with get_connection() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_token_hash(token),))
    return {"ok": True}
