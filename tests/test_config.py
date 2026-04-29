from backend.config import Settings


def test_settings_accepts_release_as_false():
    settings = Settings(
        google_api_key="test-key",
        debug="release",
        _env_file=None,
    )

    assert settings.debug is False


def test_settings_accepts_debug_as_true():
    settings = Settings(
        google_api_key="test-key",
        debug="debug",
        _env_file=None,
    )

    assert settings.debug is True


def test_settings_preserves_boolean_values():
    settings = Settings(
        google_api_key="test-key",
        debug=False,
        _env_file=None,
    )

    assert settings.debug is False
