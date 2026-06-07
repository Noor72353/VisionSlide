from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from pathlib import Path

from app.runtime_paths import data_path
from app.validators import normalize_username


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "VisionSlide@123"
DEFAULT_ADMIN_EMAIL = "admin@visionslide.local"
DEFAULT_ADMIN_RECOVERY = "visionslide"
DEFAULT_ADMIN_EMAILS = {
    DEFAULT_ADMIN_EMAIL,
}


class AuthManager:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else data_path("visionslide_auth.db")
        self.admin_emails_path = data_path("visionslide_admin_emails.json")
        self.iterations = 200_000
        self._ensure_database()

    def _load_admin_emails(self) -> set[str]:
        emails = {email.strip().lower() for email in DEFAULT_ADMIN_EMAILS if email}
        if not self.admin_emails_path.exists():
            return emails

        try:
            with open(self.admin_emails_path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
        except Exception:
            return emails

        if isinstance(loaded, list):
            for value in loaded:
                cleaned = str(value or "").strip().lower()
                if cleaned:
                    emails.add(cleaned)

        return emails

    def _save_admin_emails(self, emails: set[str]) -> None:
        cleaned_emails = sorted({str(email or "").strip().lower() for email in emails if str(email or "").strip()})
        with open(self.admin_emails_path, "w", encoding="utf-8") as file:
            json.dump(cleaned_emails, file, indent=4)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_database(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    recovery_answer_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_column(connection, "users", "email", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "users", "recovery_answer_hash", "TEXT NOT NULL DEFAULT ''")
            connection.commit()

    def _ensure_column(self, connection: sqlite3.Connection, table_name: str, column_name: str, column_definition: str) -> None:
        columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing_columns = {column[1] for column in columns}
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            )

    def has_users(self) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return row is not None

    def ensure_default_admin(self) -> None:
        if self.has_users():
            self._repair_default_admin()
            return
        self.create_user(
            DEFAULT_ADMIN_USERNAME,
            DEFAULT_ADMIN_EMAIL,
            DEFAULT_ADMIN_PASSWORD,
            DEFAULT_ADMIN_RECOVERY,
        )

    def _repair_default_admin(self) -> None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, email, recovery_answer_hash
                FROM users
                WHERE lower(username) = lower(?)
                """,
                (DEFAULT_ADMIN_USERNAME,),
            ).fetchone()

            if not row:
                return

            user_id, email, recovery_answer_hash = row
            updates: list[str] = []
            values: list[str] = []

            if not email:
                updates.append("email = ?")
                values.append(DEFAULT_ADMIN_EMAIL)

            if not recovery_answer_hash:
                updates.append("recovery_answer_hash = ?")
                values.append(self.hash_password(DEFAULT_ADMIN_RECOVERY))

            if updates:
                values.append(user_id)
                connection.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                    values,
                )
                connection.commit()

    def create_user(self, username: str, email: str, password: str, recovery_answer: str = "") -> None:
        normalized_username = normalize_username(username)
        normalized_email = (email or "").strip().lower()
        password_hash = self.hash_password(password)
        recovery_answer_hash = self.hash_password((recovery_answer or "").strip().lower())

        with self._connect() as connection:
            existing_user = connection.execute(
                "SELECT 1 FROM users WHERE lower(username) = lower(?) OR email = ?",
                (normalized_username, normalized_email),
            ).fetchone()
            if existing_user:
                raise sqlite3.IntegrityError("Username or email already exists.")
            connection.execute(
                """
                INSERT INTO users (username, email, password_hash, recovery_answer_hash)
                VALUES (?, ?, ?, ?)
                """,
                (normalized_username, normalized_email, password_hash, recovery_answer_hash),
            )
            connection.commit()

    def username_exists(self, username: str) -> bool:
        normalized_username = normalize_username(username)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM users WHERE lower(username) = lower(?)",
                (normalized_username,),
            ).fetchone()
        return row is not None

    def email_exists(self, email: str) -> bool:
        normalized_email = (email or "").strip().lower()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM users WHERE email = ?",
                (normalized_email,),
            ).fetchone()
        return row is not None

    def hash_password(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self.iterations,
        )
        return f"pbkdf2_sha256${self.iterations}${salt.hex()}${digest.hex()}"

    def verify_password(self, password: str, stored_hash: str) -> bool:
        try:
            algorithm, iterations_text, salt_hex, digest_hex = stored_hash.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            iterations = int(iterations_text)
            salt = bytes.fromhex(salt_hex)
            expected_digest = bytes.fromhex(digest_hex)
        except (TypeError, ValueError):
            return False

        calculated_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(calculated_digest, expected_digest)

    def authenticate(self, username_or_email: str, password: str) -> bool:
        normalized_value = normalize_username(username_or_email)
        normalized_email = normalized_value.lower()

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT password_hash FROM users
                WHERE lower(username) = lower(?) OR lower(email) = ?
                """,
                (normalized_value, normalized_email),
            ).fetchone()

        if not row:
            return False

        return self.verify_password(password, row[0])

    def authenticate_email(self, email: str, password: str) -> bool:
        normalized_email = (email or "").strip().lower()

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT password_hash FROM users
                WHERE lower(email) = ?
                """,
                (normalized_email,),
            ).fetchone()

        if not row:
            return False

        return self.verify_password(password, row[0])

    def get_username_for_identity(self, username_or_email: str) -> str | None:
        normalized_value = normalize_username(username_or_email)
        normalized_email = normalized_value.lower()

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT username FROM users
                WHERE lower(username) = lower(?) OR lower(email) = ?
                """,
                (normalized_value, normalized_email),
            ).fetchone()

        return row[0] if row else None

    def get_username_for_email(self, email: str) -> str | None:
        normalized_email = (email or "").strip().lower()

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT username FROM users
                WHERE lower(email) = ?
                """,
                (normalized_email,),
            ).fetchone()

        return row[0] if row else None

    def get_email_for_username(self, username: str) -> str | None:
        normalized_username = normalize_username(username)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT email FROM users
                WHERE lower(username) = lower(?)
                """,
                (normalized_username,),
            ).fetchone()

        return row[0] if row else None

    def get_login_identities(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT email
                FROM users
                ORDER BY created_at DESC, email ASC
                """
            ).fetchall()

        identities: list[str] = []
        seen: set[str] = set()
        for (email,) in rows:
            cleaned = (email or "").strip().lower()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                identities.append(cleaned)

        return identities

    def is_admin(self, username_or_email: str) -> bool:
        normalized_value = normalize_username(username_or_email)
        normalized_email = (username_or_email or "").strip().lower()
        return (
            normalized_value == DEFAULT_ADMIN_USERNAME
            or normalized_email in self._load_admin_emails()
        )

    def get_user_records(self) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT username, email, created_at
                FROM users
                ORDER BY created_at DESC, email ASC
                """
            ).fetchall()

        records: list[dict[str, str]] = []
        for username, email, created_at in rows:
            records.append(
                {
                    "username": username or "",
                    "email": (email or "").strip().lower(),
                    "created_at": created_at or "",
                }
            )
        return records

    def get_admin_emails(self) -> list[str]:
        return sorted(self._load_admin_emails())

    def add_admin_email(self, email: str) -> tuple[bool, str]:
        normalized_email = (email or "").strip().lower()
        if not normalized_email:
            return False, "Admin email is required."

        emails = self._load_admin_emails()
        if normalized_email in emails:
            return False, "This email is already in the admin list."

        emails.add(normalized_email)
        self._save_admin_emails(emails)
        return True, "Admin email added successfully."

    def remove_admin_email(self, email: str) -> tuple[bool, str]:
        normalized_email = (email or "").strip().lower()
        if not normalized_email:
            return False, "Admin email is required."

        if normalized_email in {email.strip().lower() for email in DEFAULT_ADMIN_EMAILS if email}:
            return False, "This default admin email cannot be removed."

        emails = self._load_admin_emails()
        if normalized_email not in emails:
            return False, "This email is not in the admin list."

        emails.remove(normalized_email)
        self._save_admin_emails(emails)
        return True, "Admin email removed successfully."

    def delete_user_by_email(self, email: str) -> tuple[bool, str]:
        normalized_email = (email or "").strip().lower()
        if not normalized_email:
            return False, "User email is required."

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, username
                FROM users
                WHERE lower(email) = ?
                """,
                (normalized_email,),
            ).fetchone()

            if not row:
                return False, "User account was not found."

            user_id, username = row
            if self.is_admin(username):
                return False, "The default admin account cannot be deleted."

            connection.execute(
                """
                DELETE FROM users
                WHERE id = ?
                """,
                (user_id,),
            )
            connection.commit()

        return True, "User account deleted successfully."

    def reset_password(self, email: str, new_password: str) -> bool:
        normalized_email = (email or "").strip().lower()

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id FROM users
                WHERE lower(email) = ?
                """,
                (normalized_email,),
            ).fetchone()

            if not row:
                return False

            user_id = row[0]

            connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (self.hash_password(new_password), user_id),
            )
            connection.commit()

        return True

    def update_username(self, current_username: str, current_password: str, new_username: str) -> tuple[bool, str]:
        normalized_current_username = normalize_username(current_username)
        normalized_new_username = normalize_username(new_username)

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, password_hash FROM users
                WHERE lower(username) = lower(?)
                """,
                (normalized_current_username,),
            ).fetchone()

            if not row:
                return False, "Current user not found."

            user_id, password_hash = row

            if not self.verify_password(current_password, password_hash):
                return False, "Current password is incorrect."

            existing_row = connection.execute(
                """
                SELECT id FROM users
                WHERE lower(username) = lower(?)
                """,
                (normalized_new_username,),
            ).fetchone()

            if existing_row and existing_row[0] != user_id:
                return False, "This username is already registered."

            connection.execute(
                """
                UPDATE users
                SET username = ?
                WHERE id = ?
                """,
                (normalized_new_username, user_id),
            )
            connection.commit()

        return True, "Username updated successfully."

    def update_password(self, email: str, current_password: str, new_password: str) -> tuple[bool, str]:
        normalized_email = (email or "").strip().lower()

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, password_hash FROM users
                WHERE lower(email) = ?
                """,
                (normalized_email,),
            ).fetchone()

            if not row:
                return False, "Current user not found."

            user_id, password_hash = row

            if not self.verify_password(current_password, password_hash):
                return False, "Current password is incorrect."

            connection.execute(
                """
                UPDATE users
                SET password_hash = ?
                WHERE id = ?
                """,
                (self.hash_password(new_password), user_id),
            )
            connection.commit()

        return True, "Password updated successfully."

    def update_email(self, current_username: str, current_password: str, new_email: str) -> tuple[bool, str]:
        normalized_username = normalize_username(current_username)
        normalized_email = (new_email or "").strip().lower()

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, password_hash FROM users
                WHERE lower(username) = lower(?)
                """,
                (normalized_username,),
            ).fetchone()

            if not row:
                return False, "Current user not found."

            user_id, password_hash = row

            if not self.verify_password(current_password, password_hash):
                return False, "Current password is incorrect."

            existing_row = connection.execute(
                """
                SELECT id FROM users
                WHERE lower(email) = ?
                """,
                (normalized_email,),
            ).fetchone()

            if existing_row and existing_row[0] != user_id:
                return False, "This email is already registered."

            connection.execute(
                """
                UPDATE users
                SET email = ?
                WHERE id = ?
                """,
                (normalized_email, user_id),
            )
            connection.commit()

        return True, "Email updated successfully."
