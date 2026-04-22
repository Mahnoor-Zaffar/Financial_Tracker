import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "instance" / "finance_tracker.db"
load_dotenv(BASE_DIR / ".env")


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _database_uri() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql://", 1)
        return database_url
    return f"sqlite:///{DEFAULT_DB_PATH}"


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-this-secret-key")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 4

    TRANSACTIONS_PER_PAGE = int(os.getenv("TRANSACTIONS_PER_PAGE", "20"))
    MAX_TRANSACTIONS_PER_PAGE = int(os.getenv("MAX_TRANSACTIONS_PER_PAGE", "100"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    AUTH_LOGIN_WINDOW_SECONDS = int(os.getenv("AUTH_LOGIN_WINDOW_SECONDS", "900"))
    AUTH_LOGIN_COOLDOWN_SECONDS = int(os.getenv("AUTH_LOGIN_COOLDOWN_SECONDS", "900"))
    AUTH_LOGIN_IP_LIMIT = int(os.getenv("AUTH_LOGIN_IP_LIMIT", "10"))
    AUTH_LOGIN_ACCOUNT_LIMIT = int(os.getenv("AUTH_LOGIN_ACCOUNT_LIMIT", "5"))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE", default=False)
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "fintrack_session")
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    PREFERRED_URL_SCHEME = "https" if SESSION_COOKIE_SECURE else "http"


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


def get_config(name: str | None):
    config_map = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "testing": TestingConfig,
    }
    resolved = (name or os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "development").lower()
    return config_map.get(resolved, DevelopmentConfig)
