import os

basedir = os.path.abspath(os.path.dirname(__file__))


def _normalize_db_url(url: str) -> str:
    # Render/Neon often provide postgres:// — SQLAlchemy needs postgresql://
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _env(key, default=None):
    """Treat blank env values (e.g. unset Render var left as '') as unset."""
    val = os.environ.get(key)
    if val is None or val.strip() == "":
        return default
    return val


class Config:
    APP_NAME = "Ti10-Waves"

    SECRET_KEY = _env("SECRET_KEY", "dev-secret-key-change-in-production")

    _db_url = _env("DATABASE_URL")
    if _db_url:
        SQLALCHEMY_DATABASE_URI = _normalize_db_url(_db_url)
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(basedir, "database", "app.db")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Neon (and most serverless/pooled Postgres) drop idle connections.
    # Without pool_pre_ping, SQLAlchemy can hand back a dead connection and
    # the next DB write 500s. This checks the connection is alive first and
    # transparently reconnects if not.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    UPLOAD_FOLDER = os.path.join(basedir, "static", "uploads")
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB
    ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "png", "jpg", "jpeg"}

    # Default admin account — same naming convention as Ti10 (KITCSE / CSE4321).
    # Admin logs in with a username (no email required).
    DEFAULT_ADMIN_NAME = _env("DEFAULT_ADMIN_NAME", "Administrator")
    DEFAULT_ADMIN_USERNAME = _env("DEFAULT_ADMIN_USERNAME", "KITCSE")
    DEFAULT_ADMIN_EMAIL = _env("DEFAULT_ADMIN_EMAIL")  # optional, may be left blank
    DEFAULT_ADMIN_PASSWORD = _env("DEFAULT_ADMIN_PASSWORD", "CSE4321")

    # Display timezone for timestamps (IST, same as Ti10)
    DISPLAY_TZ_OFFSET_HOURS = 5
    DISPLAY_TZ_OFFSET_MINUTES = 30
