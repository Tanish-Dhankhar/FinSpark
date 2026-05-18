"""
FinSpark Database Connection
Provides a psycopg2-based sync connection pool for use across all services and the pipeline.
The pipeline runs synchronously in background threads, so psycopg2 (sync) is the right choice.

Enterprise isolation:
  - Connections for client-scoped queries use the 'finspark_app' role (non-superuser),
    which is subject to PostgreSQL Row-Level Security policies.
  - Before any client-scoped query, the session variable 'app.current_client_id' is set
    so that RLS policies can filter rows automatically.
  - Schema migrations use the superuser 'finspark' role, which bypasses RLS intentionally.
"""
import os
import psycopg2
import psycopg2.pool
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# ── Connection URLs ────────────────────────────────────────────────────────────

# Superuser URL — used ONLY for schema DDL (init_db). RLS is bypassed for superusers.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://finspark:finspark123@localhost:5432/finspark_db"
)

# App role URL — used for all application queries. Subject to Row-Level Security.
DATABASE_APP_URL = os.getenv(
    "DATABASE_APP_URL",
    "postgresql://finspark_app:finspark_app_2024@localhost:5432/finspark_db"
)

# ── Connection Pools ───────────────────────────────────────────────────────────

# Superuser pool — schema operations only
_admin_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

# App-role pool — all runtime queries (RLS enforced)
_app_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def _get_admin_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _admin_pool
    if _admin_pool is None or _admin_pool.closed:
        _admin_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=3, dsn=DATABASE_URL,
        )
    return _admin_pool


def _get_app_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _app_pool
    if _app_pool is None or _app_pool.closed:
        _app_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2, maxconn=20, dsn=DATABASE_APP_URL,
        )
    return _app_pool


# ── Context Managers ───────────────────────────────────────────────────────────

@contextmanager
def get_db():
    """
    General-purpose context manager — yields a connection from the APP pool.
    RLS is enforced but app.current_client_id is NOT set here.
    Use this only for cross-client admin operations (list_projects, create_project).

    For all single-client operations, use get_db_for_client() instead.

    Usage:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ...")
    """
    pool = _get_app_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def get_db_for_client(client_id: str):
    """
    Client-scoped context manager — yields a connection with the RLS session variable set.

    This is the REQUIRED way to run any query that touches a single client's data.
    PostgreSQL RLS policies enforce that only rows where client_id = app.current_client_id
    are visible/writable, providing a second line of defence against application-layer bugs.

    Usage:
        with get_db_for_client(client_id) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM config_versions WHERE client_id = %s", (client_id,))
    """
    pool = _get_app_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Set session-local variable consumed by RLS policies.
            # 'LOCAL' means it's reset automatically at transaction end.
            cur.execute(
                "SET LOCAL app.current_client_id = %s",
                (client_id,),
            )
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def get_admin_db():
    """
    Admin (superuser) context manager — bypasses RLS.
    Use ONLY for schema DDL in init_db().
    """
    pool = _get_admin_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ── Schema Initialisation ──────────────────────────────────────────────────────

def init_db():
    """
    Create all FinSpark tables if they don't already exist.
    Also ensures RLS is enabled and policies are in place.
    Called once at application startup via the superuser connection.
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS projects (
        id          SERIAL PRIMARY KEY,
        client_id   VARCHAR(50)  UNIQUE NOT NULL,
        client_name VARCHAR(200) NOT NULL,
        created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        industry    VARCHAR(100),
        region      VARCHAR(100)
    );

    CREATE TABLE IF NOT EXISTS config_versions (
        id             SERIAL PRIMARY KEY,
        client_id      VARCHAR(50) NOT NULL REFERENCES projects(client_id) ON DELETE CASCADE,
        version_number INTEGER NOT NULL,
        version_label  VARCHAR(10) NOT NULL,
        config_data    JSONB NOT NULL,
        status         VARCHAR(50) DEFAULT 'draft',
        created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(client_id, version_number)
    );

    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id                    SERIAL PRIMARY KEY,
        client_id             VARCHAR(50) NOT NULL REFERENCES projects(client_id) ON DELETE CASCADE,
        run_id                VARCHAR(50) UNIQUE NOT NULL,
        triggered_by          VARCHAR(100),
        triggered_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at          TIMESTAMPTZ,
        overall_status        VARCHAR(50) DEFAULT 'pending',
        current_stage         VARCHAR(50),
        progress_percent      INTEGER DEFAULT 0,
        progress_message      TEXT,
        correction_iterations INTEGER DEFAULT 0,
        reasoning_report      TEXT,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS audit_events (
        id          SERIAL PRIMARY KEY,
        client_id   VARCHAR(50) NOT NULL REFERENCES projects(client_id) ON DELETE CASCADE,
        timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        stage       VARCHAR(100) NOT NULL,
        action      TEXT NOT NULL,
        agent       VARCHAR(100) DEFAULT 'system',
        responsible VARCHAR(100) DEFAULT 'system',
        input_hash  VARCHAR(80),
        output_hash VARCHAR(80),
        details     TEXT
    );

    CREATE TABLE IF NOT EXISTS credentials (
        id         SERIAL PRIMARY KEY,
        client_id  VARCHAR(50) NOT NULL REFERENCES projects(client_id) ON DELETE CASCADE,
        var_name   VARCHAR(200) NOT NULL,
        var_value  TEXT NOT NULL DEFAULT '',
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(client_id, var_name)
    );

    CREATE TABLE IF NOT EXISTS simulation_reports (
        id             SERIAL PRIMARY KEY,
        client_id      VARCHAR(50) NOT NULL REFERENCES projects(client_id) ON DELETE CASCADE,
        run_id         VARCHAR(50),
        report_data    JSONB NOT NULL,
        fidelity_score FLOAT,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS documents (
        id          SERIAL PRIMARY KEY,
        client_id   VARCHAR(50) NOT NULL REFERENCES projects(client_id) ON DELETE CASCADE,
        filename    VARCHAR(500) NOT NULL,
        file_path   TEXT NOT NULL,
        size_bytes  INTEGER,
        uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_config_versions_client ON config_versions(client_id, version_number DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_events_client    ON audit_events(client_id, timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_pipeline_runs_client   ON pipeline_runs(client_id);
    CREATE INDEX IF NOT EXISTS idx_credentials_client     ON credentials(client_id);
    CREATE INDEX IF NOT EXISTS idx_documents_client       ON documents(client_id);
    CREATE INDEX IF NOT EXISTS idx_sim_reports_client     ON simulation_reports(client_id);
    """

    rls_sql = """
    -- Ensure finspark_app role exists
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finspark_app') THEN
            CREATE ROLE finspark_app WITH LOGIN PASSWORD 'finspark_app_2024'
                NOSUPERUSER NOCREATEDB NOCREATEROLE;
        END IF;
    END$$;

    GRANT USAGE ON SCHEMA public TO finspark_app;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO finspark_app;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO finspark_app;

    -- Enable RLS on client-scoped tables (idempotent)
    ALTER TABLE config_versions     ENABLE ROW LEVEL SECURITY;
    ALTER TABLE pipeline_runs       ENABLE ROW LEVEL SECURITY;
    ALTER TABLE audit_events        ENABLE ROW LEVEL SECURITY;
    ALTER TABLE credentials         ENABLE ROW LEVEL SECURITY;
    ALTER TABLE simulation_reports  ENABLE ROW LEVEL SECURITY;
    ALTER TABLE documents           ENABLE ROW LEVEL SECURITY;
    ALTER TABLE projects            ENABLE ROW LEVEL SECURITY;

    -- RLS policies for finspark_app (non-superuser, subject to RLS)
    -- config_versions
    DROP POLICY IF EXISTS client_isolation_config ON config_versions;
    CREATE POLICY client_isolation_config ON config_versions
        FOR ALL TO finspark_app
        USING      (client_id = current_setting('app.current_client_id', TRUE))
        WITH CHECK (client_id = current_setting('app.current_client_id', TRUE));

    -- pipeline_runs
    DROP POLICY IF EXISTS client_isolation_pipeline ON pipeline_runs;
    CREATE POLICY client_isolation_pipeline ON pipeline_runs
        FOR ALL TO finspark_app
        USING      (client_id = current_setting('app.current_client_id', TRUE))
        WITH CHECK (client_id = current_setting('app.current_client_id', TRUE));

    -- audit_events
    DROP POLICY IF EXISTS client_isolation_audit ON audit_events;
    CREATE POLICY client_isolation_audit ON audit_events
        FOR ALL TO finspark_app
        USING      (client_id = current_setting('app.current_client_id', TRUE))
        WITH CHECK (client_id = current_setting('app.current_client_id', TRUE));

    -- credentials
    DROP POLICY IF EXISTS client_isolation_creds ON credentials;
    CREATE POLICY client_isolation_creds ON credentials
        FOR ALL TO finspark_app
        USING      (client_id = current_setting('app.current_client_id', TRUE))
        WITH CHECK (client_id = current_setting('app.current_client_id', TRUE));

    -- simulation_reports
    DROP POLICY IF EXISTS client_isolation_simreport ON simulation_reports;
    CREATE POLICY client_isolation_simreport ON simulation_reports
        FOR ALL TO finspark_app
        USING      (client_id = current_setting('app.current_client_id', TRUE))
        WITH CHECK (client_id = current_setting('app.current_client_id', TRUE));

    -- documents
    DROP POLICY IF EXISTS client_isolation_docs ON documents;
    CREATE POLICY client_isolation_docs ON documents
        FOR ALL TO finspark_app
        USING      (client_id = current_setting('app.current_client_id', TRUE))
        WITH CHECK (client_id = current_setting('app.current_client_id', TRUE));

    DROP POLICY IF EXISTS client_isolation_project ON projects;
    DROP POLICY IF EXISTS client_insert_project    ON projects;
    DROP POLICY IF EXISTS client_update_project    ON projects;
    CREATE POLICY client_isolation_project ON projects
        FOR SELECT TO finspark_app
        USING (client_id = current_setting('app.current_client_id', TRUE));
    CREATE POLICY client_insert_project ON projects
        FOR INSERT TO finspark_app
        WITH CHECK (TRUE);
    CREATE POLICY client_update_project ON projects
        FOR UPDATE TO finspark_app
        USING (client_id = current_setting('app.current_client_id', TRUE));
    """

    with get_admin_db() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
            cur.execute(rls_sql)

    print("  [DB] All FinSpark tables initialised OK")
    print("  [DB] Row-Level Security policies enforced on all client-scoped tables")
