from app.config import Settings


def _production_settings(**overrides) -> Settings:
    values = {
        "APP_MODE": "production",
        "DATABASE_URL": "postgresql+psycopg://riskroute:secret@db.example/riskroute",
        "MAPBOX_ACCESS_TOKEN": "server-token",
        "ALLOW_MOCK_MAPBOX": False,
        "SEED_DEMO_DATA": False,
        "CORS_ORIGINS": "https://riskroute.example",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_accepts_exact_https_cors_origins() -> None:
    settings = _production_settings(
        CORS_ORIGINS="https://riskroute.example,https://www.riskroute.example"
    )
    assert settings.production_configuration_errors() == []


def test_production_rejects_unsafe_or_non_origin_cors_values() -> None:
    settings = _production_settings(
        CORS_ORIGINS=(
            "*,http://riskroute.example,https://riskroute.example/path,"
            "https://localhost,https://127.0.0.1"
        )
    )
    errors = settings.production_configuration_errors()
    assert sum("exact HTTPS origin" in error for error in errors) == 3
    assert sum("localhost or loopback" in error for error in errors) == 2
