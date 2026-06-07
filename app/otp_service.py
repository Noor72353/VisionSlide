from __future__ import annotations

import random
import time


class OTPService:
    def __init__(self, expiry_seconds: int = 300):
        self.expiry_seconds = expiry_seconds
        self.pending_codes: dict[str, tuple[str, float]] = {}

    def generate_for_email(self, email: str) -> str:
        code = f"{random.randint(0, 999999):06d}"
        self.pending_codes[email.strip().lower()] = (code, time.time() + self.expiry_seconds)
        return code

    def verify_for_email(self, email: str, code: str) -> bool:
        return self.verify_status_for_email(email, code) == "valid"

    def verify_status_for_email(self, email: str, code: str) -> str:
        normalized_email = email.strip().lower()
        pending = self.pending_codes.get(normalized_email)
        if not pending:
            return "wrong"

        expected_code, expires_at = pending
        if time.time() > expires_at:
            self.pending_codes.pop(normalized_email, None)
            return "expired"

        if code.strip() != expected_code:
            return "wrong"

        return "valid"

    def clear_for_email(self, email: str) -> None:
        self.pending_codes.pop(email.strip().lower(), None)
