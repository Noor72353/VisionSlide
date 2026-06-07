from __future__ import annotations

import re

DEFAULT_USERNAME_MIN_LENGTH = 4
DEFAULT_USERNAME_MAX_LENGTH = 20
DEFAULT_PASSWORD_MIN_LENGTH = 8
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,19}$")
PASSWORD_UPPER_PATTERN = re.compile(r"[A-Z]")
PASSWORD_LOWER_PATTERN = re.compile(r"[a-z]")
PASSWORD_DIGIT_PATTERN = re.compile(r"\d")
PASSWORD_SPECIAL_PATTERN = re.compile(r"[^A-Za-z0-9\s]")
ACRONYM_WORDS = {"otp": "OTP"}
LOWERCASE_MESSAGE_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def validate_username(username: str) -> list[str]:
    normalized = normalize_username(username)
    errors: list[str] = []

    if not normalized:
        errors.append("Username is required.")
    elif normalized[0].isdigit():
        errors.append("Username cannot start with digits.")
    elif " " in normalized:
        errors.append("Spaces are not allowed in username.")
    elif not normalized[0].isalpha():
        errors.append("Special characters are not allowed.")
    elif any(not (char.isalnum() or char == "_") for char in normalized):
        errors.append("Special characters are not allowed.")
    elif len(normalized) < DEFAULT_USERNAME_MIN_LENGTH:
        errors.append("Username must be at least 4 characters.")
    elif len(normalized) > DEFAULT_USERNAME_MAX_LENGTH:
        errors.append("Username cannot exceed 20 characters.")
    elif not USERNAME_PATTERN.match(normalized):
        errors.append("Use only letters, numbers, and underscore.")

    return errors


def validate_password(password: str) -> list[str]:
    errors: list[str] = []
    password = password or ""

    if not password:
        errors.append("Password is required.")
    elif len(password) < DEFAULT_PASSWORD_MIN_LENGTH:
        errors.append("Password must be at least 8 characters.")
    elif not PASSWORD_LOWER_PATTERN.search(password):
        errors.append("Password must include at least one lowercase letter.")
    elif not PASSWORD_UPPER_PATTERN.search(password):
        errors.append("Password must include at least one uppercase letter.")
    elif not PASSWORD_DIGIT_PATTERN.search(password):
        errors.append("Password must include at least one digit.")
    elif not PASSWORD_SPECIAL_PATTERN.search(password):
        errors.append("Password must include at least one special character.")

    return errors


def get_password_strength_feedback(password: str) -> tuple[str, str]:
    password = password or ""
    if not password:
        return "empty", ""

    errors = validate_password(password)
    if errors:
        return "weak", errors[0]

    return "strong", "Strong password."


def validate_email(email: str) -> list[str]:
    email = (email or "").strip()
    errors: list[str] = []

    if not email:
        errors.append("Email is required.")
    elif not EMAIL_PATTERN.match(email):
        errors.append("Enter a valid email address.")

    return errors


def validate_confirm_password(password: str, confirm_password: str) -> list[str]:
    if (password or "") != (confirm_password or ""):
        return ["Passwords do not match."]
    return []


def validate_login_credentials(username: str, password: str) -> list[str]:
    return [*validate_username(username), *validate_password(password)]


def validate_signup_credentials(
    username: str,
    email: str,
    password: str,
    confirm_password: str,
) -> list[str]:
    return [
        *validate_username(username),
        *validate_email(email),
        *validate_password(password),
        *validate_confirm_password(password, confirm_password),
    ]


def validate_password_reset(
    email: str,
    new_password: str,
    confirm_password: str,
) -> list[str]:
    return [
        *validate_email(email),
        *validate_password(new_password),
        *validate_confirm_password(new_password, confirm_password),
    ]


def format_validation_message(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return ""

    text = re.sub(r"\bincorrect\b", "invalid", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcorrect\b", "valid", text, flags=re.IGNORECASE)
    text = re.sub(r"\bwrong\b", "invalid", text, flags=re.IGNORECASE)
    email_tokens: dict[str, str] = {}

    def preserve_email(match: re.Match) -> str:
        token = f"__EMAIL_TOKEN_{len(email_tokens)}__"
        email_tokens[token] = match.group(0).lower()
        return token

    text = re.sub(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b", preserve_email, text)
    text = text.replace(".", "")

    formatted_words: list[str] = []
    words = text.split()
    for index, word in enumerate(words):
        normalized_word = word.lower()
        if word in email_tokens:
            formatted_words.append(email_tokens[word])
        elif normalized_word in ACRONYM_WORDS:
            formatted_words.append(ACRONYM_WORDS[normalized_word])
        elif index > 0 and normalized_word in LOWERCASE_MESSAGE_WORDS:
            formatted_words.append(normalized_word)
        else:
            formatted_words.append(word[:1].upper() + word[1:].lower() if word else word)

    return " ".join(formatted_words)


def sanitize_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default


def sanitize_int(value, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return max(minimum, min(maximum, parsed))


def sanitize_float(value, minimum: float, maximum: float, default: float, decimals: int = 1) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default

    clamped = max(minimum, min(maximum, parsed))
    return round(clamped, decimals)


def sanitize_camera_index(value, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return parsed if parsed >= 0 else default


def sanitize_control_hold_frames(value, default: int = 3) -> int:
    return sanitize_int(value, 1, 10, default)


def sanitize_jump_hold_seconds(value, default: float = 1.5) -> float:
    return sanitize_float(value, 0.1, 3.0, default, decimals=1)


def sanitize_total_slides(value, default: int = 100) -> int:
    return sanitize_int(value, 1, 500, default)


def sanitize_voice_device_name(value, allowed_devices: list[str] | None = None, default: str = "Default System Microphone") -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return default

    if allowed_devices is not None and cleaned not in allowed_devices:
        return default

    return cleaned
