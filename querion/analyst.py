"""The analyst brain: reasoning, the directive protocol, and the run loop.

Querion thinks like a senior analyst. Each turn it emits one or more read-only
directives; the runner executes them and feeds the results back, until it gives
a final answer. The directives:

  ```run-sql            -> a single read-only SELECT / WITH against Postgres
  <SELECT ...>
  ```

  ```source:NAME        -> a GET against a configured HTTP source (NAME)
  GET /path?query
  ```

  ```chart              -> render a chart from data already fetched
  {"type":"bar","title":"...","x":[...],"series":[{"name":"...","values":[...]}]}
  ```

The final answer carries NO execute fence; a plain ```sql block in the answer is
display-only transparency and is never run.
"""

import datetime
import re

from querion import charts, db, llm
from querion.knowledge import build_knowledge
from querion.safety import MARKER

DIRECTIVE_RE = re.compile(
    r"```(run-sql|chart|source:[A-Za-z0-9_-]+)\s*(.+?)```",
    re.DOTALL | re.IGNORECASE,
)


def directives(reply: str, *, limit: int = 4):
    """All execute directives in a reply, in order: [(kind, body), ...].

    kind is 'sql', 'chart', or 'source:<name>'. Capped to bound a turn's fan-out.
    """
    out = []
    for m in DIRECTIVE_RE.finditer(reply or ""):
        kind = m.group(1).lower()
        if kind == "run-sql":
            kind = "sql"
        out.append((kind, m.group(2).strip()))
        if len(out) >= limit:
            break
    return out


def _today_line() -> str:
    now = datetime.datetime.now()
    iso = now.isocalendar()
    return (
        f"Today is {now.strftime('%A')} {now.date().isoformat()} "
        f"(ISO year {iso[0]}, week {iso[1]}). Resolve relative dates against this, "
        "and flag the current period as partial when comparing to closed ones."
    )


def build_system(config, knowledge_text: str) -> str:
    source_lines = "\n".join(
        f"- ```source:{s.name}``` then `GET /path` (base {s.base_url})"
        for s in config.sources
    ) or "- (no HTTP sources configured; use Postgres only)"
    return (
        f"You are Querion, an elite, strictly READ-ONLY data analyst for "
        f"{config.company}, answering in chat. You clarify the metric, pick the "
        "right source, compute it precisely, and explain the insight like a senior "
        "analyst.\n\n"
        f"## Today\n{_today_line()}\n\n"
        "## How you act (execute directives)\n"
        "You cannot run code or call tools yourself. To DO something you emit a "
        "fenced directive; the system runs it read-only and returns the result as "
        "the next message. A short sentence of preamble before a fence is fine.\n"
        "- Postgres (default): ```run-sql then a single read-only SELECT or WITH.\n"
        "- Live HTTP sources (GET only):\n" + source_lines + "\n"
        "- Chart: ```chart then a JSON spec "
        "{\"type\":\"bar\"|\"line\"|\"pie\",\"title\":\"...\",\"x\":[...],"
        "\"series\":[{\"name\":\"...\",\"values\":[...]}]}.\n\n"
        "You may emit up to 4 INDEPENDENT directives in one reply (results come "
        "back labelled in order). Keep dependent reads for the next turn. When you "
        "are done, give the FINAL ANSWER with NO execute fence - that is how the "
        "system knows you finished. Show the query you ran in a plain ```sql block "
        "for transparency (display only, never re-run; that is why the run fence is "
        "```run-sql, not ```sql).\n\n"
        "## Read-only covenant (absolute)\n"
        "You NEVER modify data anywhere. Postgres is SELECT/WITH only; HTTP is GET "
        "only. The only thing you produce is the answer. If the user asks you to "
        "change ANY data (insert, update, delete, cancel, create, set, sync, mark), "
        "do NOT run anything: reply with a single line starting EXACTLY with "
        + MARKER + " and a short note of what write was requested. Questions ABOUT "
        "past changes ('which records were cancelled?') are normal analytics; "
        "answer those.\n\n"
        "## Rules\n"
        "- Use REAL table/column names from the schema; never guess. If unsure, "
        "introspect with a small SELECT against information_schema.\n"
        "- Charts: cap to ~8 meaningful series; for high-cardinality breakdowns use "
        "the top N or a coarser dimension. Chart only data you fetched.\n"
        "- Format numbers with thousands separators and currency symbols. Lead with "
        "a one-line headline, then a compact table, then the query. Be honest about "
        "caveats (nulls, partial periods).\n\n"
        "================ KNOWLEDGE ================\n" + knowledge_text
    )


def step(config, knowledge_text: str, transcript: str, *, timeout: int = 200) -> str:
    return llm.step(
        build_system(config, knowledge_text), transcript,
        model=config.model, binary=config.claude_bin, timeout=timeout,
    )


def run_directive(kind, body, *, config, sources, charts_out, sqls, render_charts=True):
    """Execute one read-only directive. Returns text to feed back to the brain.

    charts_out collects chart specs (for clients that render them); sqls collects
    the SQL run (for transparency).
    """
    if kind == "sql":
        sql = body.rstrip(";").strip()
        cols, rows, trunc, err = db.query(
            config.database.dsn, sql,
            row_cap=config.database.row_cap,
            statement_timeout_ms=config.database.statement_timeout_ms,
        )
        if err:
            return f"SQL error: {err}"
        sqls.append(sql)
        head = rows[:30]
        table = _text_table(cols, head, trunc or len(rows) > 30)
        return f"{len(rows)} row(s){' (capped)' if trunc else ''}:\n{table}"
    if kind.startswith("source:"):
        name = kind.split(":", 1)[1]
        src = sources.get(name)
        if not src:
            return f"unknown source '{name}'. Configured: {', '.join(sources) or 'none'}"
        try:
            return src.get(body)
        except Exception as exc:  # noqa: BLE001
            return f"{name} GET failed: {exc}"
    if kind == "chart":
        import json
        try:
            spec = json.loads(body)
        except ValueError as exc:
            return f"chart spec was not valid JSON ({exc}); continue with a text answer."
        charts_out.append(spec)
        if render_charts:
            try:
                path = charts.render(spec)
                return f"Chart rendered to {path}."
            except Exception:  # noqa: BLE001
                tc = charts.text_chart(spec)
                return ("Image render unavailable; a text chart is available. "
                        + (tc or "")) if tc else "Chart could not be rendered."
        return "Chart spec captured for the client to render."
    return f"unknown directive: {kind}"


def _text_table(columns, rows, truncated):
    if not columns:
        return "(no result set)"
    if not rows:
        return "(0 rows)"
    widths = [len(str(c)) for c in columns]
    for r in rows:
        for i, v in enumerate(r):
            widths[i] = min(max(widths[i], len(str(v))), 40)
    line = lambda cells: "  ".join(str(c)[:40].ljust(widths[i]) for i, c in enumerate(cells))
    out = [line(columns), "  ".join("-" * w for w in widths)]
    out += [line(r) for r in rows]
    if truncated:
        out.append("... (more rows)")
    return "```\n" + "\n".join(out) + "\n```"
