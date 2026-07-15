"""Tests for client-side credential validation."""

from __future__ import annotations

from ai_caster.auth.validators import (
    validate_email,
    validate_login,
    validate_password,
    validate_signup,
)


def test_valid_email_passes():
    assert validate_email("caster@example.com") is None


def test_invalid_emails_are_rejected():
    assert validate_email("") is not None
    assert validate_email("not-an-email") is not None
    assert validate_email("a@b") is not None  # no dot in domain
    assert validate_email("a b@c.com") is not None  # space


def test_password_length_enforced():
    assert validate_password("short") is not None
    assert validate_password("longenough") is None
    assert validate_password("") is not None


def test_validate_signup_reports_first_problem():
    assert validate_signup("bad", "longenough") is not None  # email problem first
    assert validate_signup("ok@example.com", "short") is not None  # then password
    assert validate_signup("ok@example.com", "longenough") is None


def test_validate_login_is_lighter():
    assert validate_login("", "") is not None
    assert validate_login("ok@example.com", "x") is None  # length not enforced on login
    assert validate_login("bad", "x") is not None
