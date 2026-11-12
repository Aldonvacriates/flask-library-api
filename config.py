import os
from datetime import timedelta
from urllib.parse import quote_plus


def _first_env(*names):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _normalize_database_url(url):
    if not url:
        return url

    if url.startswith("mysql://"):
        return url.replace("mysql://", "mysql+mysqlconnector://", 1)

    return url


def _build_mysql_url_from_parts():
    host = _first_env("MYSQLHOST", "MYSQL_HOST")
    port = _first_env("MYSQLPORT", "MYSQL_PORT", "DB_PORT") or "3306"
    user = _first_env("MYSQLUSER", "MYSQL_USER")
    password = _first_env("MYSQLPASSWORD", "MYSQL_PASSWORD")
    database = _first_env("MYSQLDATABASE", "MYSQL_DATABASE")

    if not all([host, user, password, database]):
        return None

    return (
        "mysql+mysqlconnector://"
        f"{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}"
    )


def _database_url(default):
    configured_url = _first_env("DATABASE_URL", "MYSQL_URL", "MYSQL_PUBLIC_URL")
    if configured_url:
        return _normalize_database_url(configured_url)

    mysql_url = _build_mysql_url_from_parts()
    if mysql_url:
        return mysql_url

    return default


def _redis_url(default):
    return _first_env("REDIS_URL", "REDIS_PUBLIC_URL") or default


# Fallback used only when no database env vars are set. It contains no
# password: set DATABASE_URL (see .env.example) for a real connection.
# ProductionConfig refuses to boot with this value (app/__init__.py).
LOCAL_DATABASE_URL = "mysql+mysqlconnector://root@localhost/library_db"


# -----------------------------------------------------
# Base configuration
# This class contains settings shared across all
# environments (development, testing, production)
# -----------------------------------------------------
class BaseConfig:

    # Disable modification tracking to save memory and
    # improve performance when using SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Default cache expiration time (in seconds)
    CACHE_DEFAULT_TIMEOUT = 60

    # Prevent cache failures from breaking the application
    CACHE_IGNORE_ERRORS = True

    # Prefix for cache keys to avoid collisions with
    # other applications using the same Redis instance
    CACHE_KEY_PREFIX = "my_library:"

    # Redis connection used for caching
    # First tries CACHE_REDIS_URL, then REDIS_URL,
    # otherwise defaults to local Redis instance
    CACHE_REDIS_URL = os.getenv("CACHE_REDIS_URL", _redis_url("redis://localhost:6379/1"))

    # Secret key used to sign JWT tokens
    # Should always be replaced with a strong value
    JWT_SECRET_KEY = os.getenv(
        "JWT_SECRET_KEY",
        "replace-this-with-a-32-byte-minimum-jwt-secret",
    )

    # JWT access token expiration time
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)

    # JWT refresh token expiration time
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # Storage backend used by Flask-Limiter for rate limiting
    # Uses Redis so limits are shared across multiple workers
    RATELIMIT_STORAGE_URI = os.getenv(
        "RATELIMIT_STORAGE_URI",
        _redis_url("redis://localhost:6379/0"),
    )

    # Rate limiting algorithm
    # "moving-window" provides more accurate limits
    RATELIMIT_STRATEGY = "moving-window"

    # Enables rate-limit headers in responses
    # Example:
    # X-RateLimit-Limit
    # X-RateLimit-Remaining
    RATELIMIT_HEADERS_ENABLED = True

    # Default limits applied to all routes unless overridden
    RATELIMIT_DEFAULT = "200 per day, 50 per hour"

    # Application-wide safety limit
    RATELIMIT_APPLICATION = "1000 per hour"

    # Fallback limits used if Redis becomes unavailable
    RATELIMIT_IN_MEMORY_FALLBACK = "200 per day, 50 per hour"

    # Authentication-specific rate limits
    AUTH_LOGIN_RATE_LIMIT = "5 per minute"
    AUTH_REFRESH_RATE_LIMIT = "10 per minute"

    # Limits for heavier read operations
    HEAVY_READ_RATE_LIMIT = "20 per minute"

    # Limits for search endpoints
    SEARCH_RATE_LIMIT = "10 per minute"


# -----------------------------------------------------
# Development configuration
# Used during local development
# -----------------------------------------------------
class DevelopmentConfig(BaseConfig):

    # Simple in-memory cache for development
    CACHE_TYPE = os.getenv("CACHE_TYPE", "SimpleCache")

    # Local MySQL database connection (from DATABASE_URL or MySQL env vars)
    SQLALCHEMY_DATABASE_URI = _database_url(LOCAL_DATABASE_URL)

    # Enables Flask debug mode
    DEBUG = True

    # Allows rate limiter to fall back to in-memory limits
    # if Redis is unavailable during development
    RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = True


# -----------------------------------------------------
# Testing configuration
# Used for automated tests
# -----------------------------------------------------
class TestingConfig(BaseConfig):

    # Simple in-memory cache
    CACHE_TYPE = "SimpleCache"

    # In-memory SQLite database for fast tests
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:"
    )

    # Use in-memory rate limit storage during tests
    RATELIMIT_STORAGE_URI = "memory://"

    # Enable Flask testing mode
    TESTING = True

    # Allow fallback rate limiting
    RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = True


# -----------------------------------------------------
# Production configuration
# Used when the application is deployed
# -----------------------------------------------------
class ProductionConfig(BaseConfig):

    # Production cache should use Redis
    CACHE_TYPE = os.getenv("CACHE_TYPE", "RedisCache")

    # Production database connection (must come from the environment)
    SQLALCHEMY_DATABASE_URI = _database_url(LOCAL_DATABASE_URL)
