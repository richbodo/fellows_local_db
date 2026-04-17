"""Unit tests for deploy/magic_link_auth.py (no HTTP)."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "deploy"))

import magic_link_auth as ml  # noqa: E402


def test_sha256_email_normalizes():
    a = ml.sha256_email("  Test@Example.COM  ")
    b = ml.sha256_email("test@example.com")
    assert a == b
    assert len(a) == 64


def test_session_roundtrip(monkeypatch):
    monkeypatch.setenv("FELLOWS_SESSION_SECRET", "unit-test-secret")
    sec = ml.session_secret_bytes()
    assert sec
    v = ml.sign_session_value(sec)
    assert ml.verify_session_value(v, sec)
    assert not ml.verify_session_value(v + "x", sec)


def test_allowlist_load(tmp_path):
    p = tmp_path / "allowed_emails.json"
    p.write_text('{"hashes": ["aa", "bb"]}', encoding="utf-8")
    s = ml.load_allowlist(tmp_path)
    assert s == {"aa", "bb"}


def test_gated_paths():
    assert ml.is_gated_api_path("/api/fellows")
    assert not ml.is_gated_api_path("/api/auth/status")
    assert not ml.is_gated_api_path("/api/debug/diagnostics")
    assert ml.is_protected_data_path("/fellows.db")
    assert ml.is_protected_data_path("/images/foo.jpg")
