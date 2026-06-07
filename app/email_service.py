from __future__ import annotations

import os
import smtplib
import sys
from email.message import EmailMessage

if sys.platform.startswith("win"):
    import winreg


class EmailDeliveryError(Exception):
    pass


class EmailService:
    def __init__(self):
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 587
        self.sender_email = ""
        self.sender_password = ""
        self.refresh_config()

    def _read_windows_user_env(self, name: str) -> str:
        if not sys.platform.startswith("win"):
            return ""

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                value, _ = winreg.QueryValueEx(key, name)
                return str(value).strip()
        except OSError:
            return ""

    def refresh_config(self) -> None:
        smtp_host = os.getenv("VISIONSLIDE_SMTP_HOST", "").strip() or self._read_windows_user_env("VISIONSLIDE_SMTP_HOST")
        smtp_port = os.getenv("VISIONSLIDE_SMTP_PORT", "").strip() or self._read_windows_user_env("VISIONSLIDE_SMTP_PORT")
        sender_email = os.getenv("VISIONSLIDE_SMTP_EMAIL", "").strip() or self._read_windows_user_env("VISIONSLIDE_SMTP_EMAIL")
        sender_password = os.getenv("VISIONSLIDE_SMTP_PASSWORD", "").strip() or self._read_windows_user_env("VISIONSLIDE_SMTP_PASSWORD")

        self.smtp_host = smtp_host or "smtp.gmail.com"
        try:
            self.smtp_port = int(smtp_port or "587")
        except ValueError:
            self.smtp_port = 587
        self.sender_email = sender_email
        self.sender_password = sender_password

    def is_configured(self) -> bool:
        self.refresh_config()
        return bool(self.sender_email and self.sender_password)

    def send_otp_email(self, recipient_email: str, otp_code: str) -> None:
        self.refresh_config()
        if not self.is_configured():
            raise EmailDeliveryError(
                "OTP email is not configured yet. Set VISIONSLIDE_SMTP_EMAIL and "
                "VISIONSLIDE_SMTP_PASSWORD before sending verification codes."
            )

        message = EmailMessage()
        message["Subject"] = "VisionSlide Verification Code"
        message["From"] = self.sender_email
        message["To"] = recipient_email
        message.set_content(
            "Your VisionSlide verification code is "
            f"{otp_code}. It expires in 5 minutes."
        )

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)
        except Exception as error:
            raise EmailDeliveryError(f"Could not send OTP email: {error}") from error
