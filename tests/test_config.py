import pytest

from stockwise.config import EXAMPLE_JWT_SECRET, format_upload_limit, load_max_upload_bytes, load_settings


def test_production_requires_a_non_placeholder_long_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="must be set"):
        load_settings()

    monkeypatch.setenv("JWT_SECRET", "short-secret")
    with pytest.raises(RuntimeError, match="at least 32"):
        load_settings()

    monkeypatch.setenv("JWT_SECRET", EXAMPLE_JWT_SECRET)
    with pytest.raises(RuntimeError, match="example value"):
        load_settings()


def test_production_accepts_a_long_secret_and_configures_upload_limit(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "a-realistic-test-secret-that-is-at-least-32-chars")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "4194304")
    assert load_settings().secure_cookies is True
    assert load_max_upload_bytes() == 4 * 1024 * 1024


@pytest.mark.parametrize("value", ["0", "-4", "not-a-number"])
def test_upload_limit_must_be_a_positive_integer(value, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", value)
    with pytest.raises(RuntimeError, match="positive integer"):
        load_max_upload_bytes()


@pytest.mark.parametrize(("value", "label"), [
    (10 * 1024 * 1024, "10 MiB"),
    (4 * 1024 * 1024, "4 MiB"),
    (5_000_000, "4.8 MiB"),
    (4096, "4 KiB"),
    (500, "500 bytes"),
])
def test_upload_limit_uses_readable_binary_units(value, label):
    assert format_upload_limit(value) == label
