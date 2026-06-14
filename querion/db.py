"""Read-only Postgres access.

Connections are opened in read-only mode (set_session(readonly=True)) and run
with a server-side statement timeout, on top of the SELECT/WITH validation in
safety.py. For real isolation, point the DSN at a dedicated read-only role with
SELECT-only grants - this module is the application backstop, not a substitute
for database permissions.
"""

import psycopg2

from querion.safety import UnsafeSQLError, validate_sql


class DatabaseError(RuntimeError):
    pass


def connect(dsn: str):
    if not dsn:
        raise DatabaseError("no database DSN configured (database.dsn in querion.yaml)")
    conn = psycopg2.connect(dsn, connect_timeout=5)
    # Belt and suspenders: the session itself refuses writes even if a future
    # code path or a clever query slips past validation.
    conn.set_session(readonly=True, autocommit=True)
    return conn


def query(dsn: str, sql: str, *, row_cap: int = 500, statement_timeout_ms: int = 15000):
    """Validate + run a read-only query. Returns (columns, rows, truncated, error)."""
    try:
        validate_sql(sql)
    except UnsafeSQLError as exc:
        return [], [], False, str(exc)
    conn = None
    try:
        conn = connect(dsn)
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = %s", (int(statement_timeout_ms),))
            cur.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(row_cap + 1)
            truncated = len(rows) > row_cap
            return columns, [list(r) for r in rows[:row_cap]], truncated, ""
    except Exception as exc:  # noqa: BLE001
        return [], [], False, str(exc)
    finally:
        if conn is not None:
            conn.close()


def ping(dsn: str) -> str:
    """Return '' on a successful read-only connection, else the error text."""
    _, _, _, err = query(dsn, "SELECT 1", row_cap=1)
    return err
