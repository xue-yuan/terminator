from app.core.config import Settings


def test_neon_url_becomes_asyncpg_with_ssl(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    s = Settings(DATABASE_URL="postgresql://u:p@ep-x-pooler.ap-southeast-1.aws.neon.tech/db?sslmode=require&channel_binding=require")
    assert s.database_url.render_as_string(hide_password=False) == "postgresql+asyncpg://u:p@ep-x-pooler.ap-southeast-1.aws.neon.tech/db"
    assert s.database_connect_args == {"ssl": True, "statement_cache_size": 0}


def test_local_parts_without_ssl(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    s = Settings(DATABASE_URL="", POSTGRES_SERVER="localhost", POSTGRES_DB="x")
    assert s.database_url.drivername == "postgresql+asyncpg" and s.database_connect_args == {}
