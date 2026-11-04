import ssl

from app.db.session import normalize_database_url


def test_neon_url_is_rewritten_for_asyncpg() -> None:
    raw = (
        "postgresql://owner:pw@ep-cool-name-123456.us-east-2.aws.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )
    result = normalize_database_url(raw)
    assert result.url.startswith("postgresql+asyncpg://owner:pw@ep-cool-name-123456")
    assert "sslmode" not in result.url
    assert "channel_binding" not in result.url
    assert isinstance(result.connect_args["ssl"], ssl.SSLContext)
    assert result.connect_args["ssl"].verify_mode == ssl.CERT_REQUIRED
    assert "statement_cache_size" not in result.connect_args


def test_neon_pooler_disables_statement_cache() -> None:
    raw = "postgresql://o:p@ep-x-123-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
    result = normalize_database_url(raw)
    assert result.connect_args["statement_cache_size"] == 0
    assert "prepared_statement_cache_size=0" in result.url
    name_func = result.connect_args["prepared_statement_name_func"]
    assert name_func() != name_func()


def test_local_postgres_without_ssl() -> None:
    result = normalize_database_url("postgres://u:p@localhost:5432/routewise?sslmode=disable")
    assert result.url == "postgresql+asyncpg://u:p@localhost:5432/routewise"
    assert result.connect_args == {"ssl": False}
    assert result.dialect == "postgresql"


def test_sqlite_paths_survive() -> None:
    assert normalize_database_url("sqlite:///./dev.db").url == "sqlite+aiosqlite:///./dev.db"
    windows = "sqlite+aiosqlite:///C:/Users/x/test.db"
    result = normalize_database_url(windows)
    assert result.url == windows
    assert result.dialect == "sqlite"
