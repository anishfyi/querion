"""Knowledge assembly: what the analyst knows before it answers.

Querion's brain is only as good as the context it carries. This module builds
that context from three places:

1. The database schema - either a curated markdown file you point to, or a live
   read-only introspection of information_schema.
2. Your API docs - one markdown file per HTTP source, describing the read
   endpoints and what they return.
3. An optional Trove semantic layer (github.com/anishfyi/trove) - domain
   vocabulary, metric definitions, and relationships that Trove maintains for
   you as you work, so Querion speaks your business language.
"""

import os

from querion import db


def introspect_schema(dsn: str, *, statement_timeout_ms: int = 15000) -> str:
    """Return a markdown snapshot of public tables (read-only)."""
    cols_sql = (
        "SELECT table_name, column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_schema='public' ORDER BY table_name, ordinal_position"
    )
    columns, rows, _, err = db.query(dsn, cols_sql, row_cap=10000,
                                     statement_timeout_ms=statement_timeout_ms)
    if err:
        return f"(schema introspection failed: {err})"
    by_table = {}
    for table, col, dtype in rows:
        by_table.setdefault(table, []).append(f"{col}:{dtype}")

    pk_sql = (
        "SELECT tc.table_name, kcu.column_name "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name "
        " AND tc.table_schema = kcu.table_schema "
        "WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema='public'"
    )
    _, pk_rows, _, _ = db.query(dsn, pk_sql, row_cap=10000,
                                statement_timeout_ms=statement_timeout_ms)
    pks = {}
    for table, col in pk_rows:
        pks.setdefault(table, []).append(col)

    out = [f"_Live snapshot: {len(by_table)} tables in schema public._", ""]
    for table in sorted(by_table):
        pk = f" [PK {','.join(pks[table])}]" if table in pks else ""
        out.append(f"- `{table}`{pk} :: " + ", ".join(by_table[table]))
    return "\n".join(out)


def _read(path: str) -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def build_knowledge(config) -> str:
    """Assemble the full knowledge block injected into the system prompt."""
    parts = [f"# ORGANIZATION\nYou are the data analyst for {config.company}."]

    schema_path = config.resolve(config.database.schema_doc)
    schema = _read(schema_path) if schema_path else ""
    if not schema and config.database.dsn:
        schema = introspect_schema(
            config.database.dsn,
            statement_timeout_ms=config.database.statement_timeout_ms,
        )
    if schema:
        parts.append("# DATABASE SCHEMA\n" + schema)

    for src in config.sources:
        docs = _read(config.resolve(src.docs)) if src.docs else ""
        header = (
            f"# SOURCE: {src.name} (live HTTP, read-only GET)\n"
            f"Base URL: {src.base_url}\n"
            f"To query it: emit a ```source:{src.name}``` fence with `GET /path`."
        )
        parts.append(header + ("\n\n" + docs if docs else ""))

    if config.trove.enabled:
        layer = _read(config.resolve(config.trove.layer_path))
        if layer:
            parts.append("# SEMANTIC LAYER (maintained by Trove)\n" + layer)

    return "\n\n".join(parts)
