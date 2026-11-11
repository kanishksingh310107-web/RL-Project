"""Unit tests for app.core.config key gate and parser."""
import os
from pathlib import Path
from app.core.config import parse_dotenv, get_setting, is_geoapify_configured


def test_parse_dotenv_handles_comments_and_quotes(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Comment line\n"
        "GEOAPIFY_API_KEY=\"test_key_123\"\n"
        "EMPTY_VAL=\n"
        "SINGLE_QUOTED='single_val'\n"
        "SPACED_KEY = spaced_val \n",
        encoding="utf-8"
    )
    parsed = parse_dotenv(env_file)
    assert parsed["GEOAPIFY_API_KEY"] == "test_key_123"
    assert parsed["EMPTY_VAL"] == ""
    assert parsed["SINGLE_QUOTED"] == "single_val"
    assert parsed["SPACED_KEY"] == "spaced_val"
    assert "#" not in parsed


def test_parse_dotenv_nonexistent_file(tmp_path):
    parsed = parse_dotenv(tmp_path / "nonexistent.env")
    assert parsed == {}


def test_get_setting_prefers_os_environ(monkeypatch):
    monkeypatch.setenv("TEST_KEY_ENV", "from_os")
    assert get_setting("TEST_KEY_ENV", "default") == "from_os"


def test_get_setting_fallback_default(monkeypatch):
    monkeypatch.delenv("NON_EXISTENT_KEY_XYZ", raising=False)
    assert get_setting("NON_EXISTENT_KEY_XYZ", "default_xyz") == "default_xyz"


def test_is_geoapify_configured_boolean(monkeypatch):
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)
    # when unset or empty
    monkeypatch.setattr("app.core.config._DOTENV", {})
    assert is_geoapify_configured() is False

    monkeypatch.setenv("GEOAPIFY_API_KEY", "real_key_mock")
    assert is_geoapify_configured() is True
