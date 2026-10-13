"""Authentication, session management, and role-based access control.

Security invariants:
- Plaintext passwords are never persisted or returned in API responses.
- Passwords are securely hashed using Argon2id (via argon2-cffi).
- Session tokens are generated using cryptographically strong randomness
  (secrets.token_urlsafe) and stored only as SHA-256 hashes in the database.
- Registrations are strictly assigned the 'student' role by default.
  Role escalation via client payloads is blocked on the server.
- Researcher accounts can only be provisioned via the documented local CLI procedure.
- Authentication failures return generic messages without revealing account existence.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
import uuid

import argon2
import store

# Initialize Argon2id password hasher (RFC 9106 recommended parameters)
_hasher = argon2.PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16
)

_USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")
_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
SESSION_EXPIRY_DAYS = 7


class AuthError(Exception):
    """Base exception for authentication errors."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class DuplicateAccountError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    def __init__(self, message: str = "Invalid username or password"):
        super().__init__(message, status_code=401)


class ValidationError(AuthError):
    pass


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    try:
        return _hasher.verify(stored_hash, password)
    except (argon2.exceptions.VerifyMismatchError,
            argon2.exceptions.VerificationError,
            argon2.exceptions.InvalidHash):
        return False


def validate_username(username: str) -> str:
    username = (username or "").strip()
    if not _USERNAME_REGEX.match(username):
        raise ValidationError(
            "Username must be 3-32 characters and contain only letters, numbers, underscores, and hyphens."
        )
    return username


def validate_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_REGEX.match(email):
        raise ValidationError("Please provide a valid email address.")
    return email


def validate_password(password: str) -> None:
    if not password or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")


def register_user(username: str, email: str, password: str, requested_role: str = "student") -> dict:
    """Register a new student account.
    
    Security: The requested_role parameter is deliberately overridden to 'student'
    to prevent client-side privilege escalation.
    """
    clean_username = validate_username(username)
    clean_email = validate_email(email)
    validate_password(password)

    role = "student"  # Non-negotiable default for public registration

    user_id = "usr_" + uuid.uuid4().hex[:16]
    pwd_hash = hash_password(password)

    with store._lock, store._session() as conn:
        # Check duplicate username (case-insensitive)
        existing_user = conn.execute(
            "SELECT 1 FROM users WHERE LOWER(username) = LOWER(?)",
            (clean_username,)
        ).fetchone()
        if existing_user:
            raise DuplicateAccountError("A user with this username already exists.")

        # Check duplicate email (case-insensitive)
        existing_email = conn.execute(
            "SELECT 1 FROM users WHERE LOWER(email) = LOWER(?)",
            (clean_email,)
        ).fetchone()
        if existing_email:
            raise DuplicateAccountError("An account with this email address already exists.")

        conn.execute(
            "INSERT INTO users (user_id, username, email, password_hash, role) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, clean_username, clean_email, pwd_hash, role)
        )

    return {
        "user_id": user_id,
        "username": clean_username,
        "email": clean_email,
        "role": role,
    }


def create_researcher_user(username: str, email: str, password: str) -> dict:
    """Create or upgrade a researcher user account (safe local CLI procedure)."""
    clean_username = validate_username(username)
    clean_email = validate_email(email)
    validate_password(password)

    pwd_hash = hash_password(password)

    with store._lock, store._session() as conn:
        existing = conn.execute(
            "SELECT user_id FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)",
            (clean_username, clean_email)
        ).fetchone()

        if existing:
            uid = existing["user_id"]
            conn.execute(
                "UPDATE users SET password_hash = ?, role = 'researcher' WHERE user_id = ?",
                (pwd_hash, uid)
            )
            return {
                "user_id": uid,
                "username": clean_username,
                "email": clean_email,
                "role": "researcher",
                "action": "promoted"
            }
        else:
            uid = "usr_" + uuid.uuid4().hex[:16]
            conn.execute(
                "INSERT INTO users (user_id, username, email, password_hash, role) "
                "VALUES (?, ?, ?, ?, 'researcher')",
                (uid, clean_username, clean_email, pwd_hash)
            )
            return {
                "user_id": uid,
                "username": clean_username,
                "email": clean_email,
                "role": "researcher",
                "action": "created"
            }


def authenticate_user(username_or_email: str, password: str) -> dict:
    """Authenticate a user by username or email.
    
    Security: Returns generic error message on failure to prevent user enumeration.
    """
    identifier = (username_or_email or "").strip()
    if not identifier or not password:
        raise InvalidCredentialsError()

    with store._session() as conn:
        row = conn.execute(
            "SELECT user_id, username, email, password_hash, role, created_at "
            "FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)",
            (identifier, identifier)
        ).fetchone()

    if not row or not verify_password(row["password_hash"], password):
        raise InvalidCredentialsError()

    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "created_at": row["created_at"],
    }


def create_session(user_id: str) -> tuple[str, str, dict]:
    """Create a new authenticated session. Returns (session_token, csrf_token, session_dict)."""
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    session_id = "sess_" + uuid.uuid4().hex[:16]

    expires_at = (datetime.now(timezone.utc) + timedelta(days=SESSION_EXPIRY_DAYS)).isoformat()

    with store._lock, store._session() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, user_id, token_hash, csrf_token, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, user_id, token_hash, csrf_token, expires_at)
        )

    return raw_token, csrf_token, {
        "session_id": session_id,
        "user_id": user_id,
        "expires_at": expires_at,
        "csrf_token": csrf_token
    }


def get_session(raw_token: str) -> dict | None:
    """Validate a session token and return user information if active."""
    if not raw_token:
        return None

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    now_iso = datetime.now(timezone.utc).isoformat()

    with store._session() as conn:
        row = conn.execute(
            "SELECT s.session_id, s.user_id, s.csrf_token, s.expires_at, "
            "       u.username, u.email, u.role, u.created_at as user_created_at "
            "FROM sessions s "
            "JOIN users u ON s.user_id = u.user_id "
            "WHERE s.token_hash = ?",
            (token_hash,)
        ).fetchone()

    if not row:
        return None

    # Check expiration
    if row["expires_at"] < now_iso:
        # Expired: delete session
        with store._lock, store._session() as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (row["session_id"],))
        return None

    return {
        "session_id": row["session_id"],
        "user_id": row["user_id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "csrf_token": row["csrf_token"],
        "expires_at": row["expires_at"],
        "created_at": row["user_created_at"]
    }


def invalidate_session(raw_token: str) -> bool:
    """Invalidate an active session."""
    if not raw_token:
        return False
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    with store._lock, store._session() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        return cur.rowcount > 0
