"""Client-side credential validation.

A first line of defence so obviously-bad input never reaches the account service
and users get an immediate, specific message. The server (Supabase) remains
authoritative — these checks only catch the easy mistakes early.
"""

from __future__ import annotations

import re

# Deliberately permissive: one @, a dot in the domain, no spaces. We are not the
# authority on deliverability — the confirmation email is.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 8


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> str | None:
    """Return an error message if ``email`` is not a plausible address, else None."""
    if not email.strip():
        return "Enter your email address."
    if not _EMAIL_RE.match(email.strip()):
        return "That doesn't look like a valid email address."
    return None


def validate_password(password: str) -> str | None:
    """Return an error message if ``password`` is too weak, else None."""
    if not password:
        return "Enter a password."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


def validate_signup(email: str, password: str) -> str | None:
    """Validate a sign-up form; return the first problem or None if it's usable."""
    return validate_email(email) or validate_password(password)


def validate_login(email: str, password: str) -> str | None:
    """Validate a sign-in form (lighter than sign-up — the server verifies)."""
    if not email.strip() or not password:
        return "Enter your email and password."
    return validate_email(email)
