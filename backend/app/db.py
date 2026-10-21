from contextlib import contextmanager

from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

from .config import settings

_pool: ConnectionPool | None = None


def init_pool() -> ConnectionPool:
    """Create the pool and make sure the schema exists."""
    global _pool

    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is empty. Add your Neon connection string to backend/.env"
        )

    # The vector extension has to exist before register_vector() can run on a connection.
    import psycopg

    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    _pool = ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=10,
        configure=register_vector,
        open=True,
    )

    with _pool.connection() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS documents (
                id          BIGSERIAL PRIMARY KEY,
                scope       TEXT NOT NULL CHECK (scope IN ('public', 'private')),
                source      TEXT NOT NULL,
                chunk_index INT  NOT NULL,
                content     TEXT NOT NULL,
                embedding   vector({settings.embedding_dim}) NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS documents_scope_idx ON documents (scope)"
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS documents_embedding_idx
            ON documents USING hnsw (embedding vector_cosine_ops)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_logs (
                id         BIGSERIAL PRIMARY KEY,
                mode       TEXT NOT NULL,
                question   TEXT NOT NULL,
                answer     TEXT NOT NULL,
                flagged    BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    return _pool


def close_pool() -> None:
    if _pool is not None:
        _pool.close()


@contextmanager
def get_conn():
    if _pool is None:
        raise RuntimeError("Database pool is not initialised")
    with _pool.connection() as conn:
        yield conn
