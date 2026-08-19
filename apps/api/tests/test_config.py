import pytest

from src.core.config import Settings


def test_cors_origins_list_splits_and_strips() -> None:
    settings = Settings(cors_origins="http://a.test, http://b.test ,http://c.test")

    assert settings.cors_origins_list == ["http://a.test", "http://b.test", "http://c.test"]


def test_production_with_default_secret_key_is_rejected() -> None:
    settings = Settings(app_env="production", secret_key="change-me-in-production")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings.validate_production_safety()


def test_production_with_real_secret_key_is_accepted() -> None:
    settings = Settings(app_env="production", secret_key="a-real-generated-secret")

    settings.validate_production_safety()  # should not raise


def test_development_with_default_secret_key_is_accepted() -> None:
    settings = Settings(app_env="development", secret_key="change-me-in-production")

    settings.validate_production_safety()  # should not raise
