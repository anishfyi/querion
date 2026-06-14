"""Read-only safety layer - the heart of Querion's contract.

Three independent guards, defense in depth:

1. SQL validation: only a single SELECT / WITH statement, with a denylist of
   data-modifying keywords (catches data-modifying CTEs like
   `WITH x AS (DELETE ... RETURNING ...) SELECT ...`).
2. HTTP allowlist: GET only, and on APIs that expose state-changing operations
   over GET, a positive per-source allowlist of read paths (default-deny).
3. Write-request firewall: if a USER asks Querion to change data, the request is
   refused and never reaches an executor.

None of these replaces a read-only database role and read-only API tokens - use
those too. These are the application-level backstop.
"""

import re

# --------------------------------------------------------------------------- #
# 1. SQL validation                                                           #
# --------------------------------------------------------------------------- #

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create|"
    r"comment|copy|vacuum|analyze|reindex|cluster|listen|notify|do|call|"
    r"merge|lock|set)\b",
    re.IGNORECASE,
)


class UnsafeSQLError(ValueError):
    pass


def validate_sql(sql: str):
    """Raise UnsafeSQLError unless sql is a single read-only SELECT/WITH."""
    stripped = (sql or "").strip()
    if not stripped:
        raise UnsafeSQLError("empty query")
    if ";" in stripped.rstrip(";"):
        raise UnsafeSQLError("multiple statements are not allowed")
    head = stripped.lstrip().split(None, 1)[0].lower()
    if head not in ("select", "with"):
        raise UnsafeSQLError(f"only SELECT/WITH queries are allowed (got '{head}')")
    if _FORBIDDEN.search(stripped):
        raise UnsafeSQLError("query contains a forbidden (write/DDL) keyword")


# --------------------------------------------------------------------------- #
# 2. HTTP allowlist (per source)                                             #
# --------------------------------------------------------------------------- #

class HttpReadError(RuntimeError):
    pass


def compile_allowlist(patterns):
    if not patterns:
        return None
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


def path_allowed(path: str, allowlist_re) -> bool:
    """True if the path (sans query string) passes the allowlist.

    allowlist_re None means no allowlist configured -> any GET is allowed.
    """
    if allowlist_re is None:
        return True
    head = (path or "").split("?", 1)[0].strip()
    if not head.startswith("/"):
        head = "/" + head
    return bool(allowlist_re.match(head))


def read_verb(directive: str) -> str:
    """Return the GET path from an HTTP directive, rejecting any write verb."""
    parts = (directive or "").strip().split(None, 1)
    if parts and parts[0].upper() in ("POST", "PUT", "PATCH", "DELETE"):
        raise HttpReadError(f"{parts[0].upper()} is a write and is not allowed - reads only.")
    if len(parts) == 2 and parts[0].upper() in ("GET", "HEAD"):
        return parts[1].strip()
    return (directive or "").strip()  # bare path, treated as GET


# --------------------------------------------------------------------------- #
# 3. Write-request firewall                                                  #
# --------------------------------------------------------------------------- #

# The brain prefixes its whole reply with this marker when the USER asked to
# modify data; the caller then refuses without executing anything.
MARKER = "[WRITE-REQUEST-BLOCKED]"

# Deterministic layer: unambiguous write STATEMENTS pasted into the question.
# Statement-shaped so ordinary analytics phrasing ("which orders were
# cancelled", "create a table comparing weeks") does not false-positive.
_SQL_WRITE = re.compile(
    r"(\binsert\s+into\s+\w+\s*(?:\(|values\b|select\b)|\bupdate\s+\w+\s+set\b|"
    r"\bdelete\s+from\s+\w+\s*(?:where\b|;|$)|"
    r"\btruncate\s+table\s+\w+|\bdrop\s+(?:table|schema|database|role|view)\s+\w+|"
    r"\balter\s+(?:table|role|database|system)\s+\w+|"
    r"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?\w+\s*\(|"
    r"\bcreate\s+(?:database|schema|role|extension)\s+\w+|"
    r"\bgrant\s+(?:select|all|insert|update|delete)\b|\brevoke\s+\w+\s+on\b)",
    re.IGNORECASE,
)
_GQL_MUTATION = re.compile(r"\bmutation\s*[\w({]", re.IGNORECASE)


def write_request_reason(text: str) -> str:
    """A short reason if the text contains an explicit write instruction, else ''."""
    t = text or ""
    m = _SQL_WRITE.search(t)
    if m:
        return "contains a SQL write statement: " + m.group(0)[:48]
    if _GQL_MUTATION.search(t):
        return "contains a GraphQL mutation"
    return ""
