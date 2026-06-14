# Architecture

Querion is a small, read-only loop around the Claude Code CLI.

## The loop

```
question
  -> engine.run applies the write-request firewall
  -> analyst.step asks the brain (Claude Code CLI) for read-only directives
  -> the runner executes them read-only:
       run-sql        -> querion.db   (SELECT/WITH, read-only session, timeout)
       source:NAME    -> querion.sources (GET only, per-source allowlist)
       chart          -> querion.charts (or a spec for the client to draw)
  -> results are fed back into the transcript
  -> repeat until the brain returns a final answer (no execute fence)
```

The brain never executes anything itself. It can only emit fenced directives
that the runner validates and runs. Steps are stateless: the full running
transcript is passed each turn, so there is no session to leak across users.

## Modules

| Module | Responsibility |
|---|---|
| `config.py` | Load `querion.yaml`, interpolate `${VAR}` from the environment |
| `llm.py` | Claude Code CLI wrapper (`claude -p`, tools off, strict MCP) |
| `safety.py` | SQL validation, HTTP allowlist, write-request firewall |
| `db.py` | Read-only Postgres (read-only session + statement timeout) |
| `sources.py` | Generic read-only HTTP connectors (GET + allowlist) |
| `knowledge.py` | Schema + API docs + optional Trove semantic layer |
| `charts.py` | Colored chart rendering with a unicode fallback |
| `limits.py` | Per-user daily question cap |
| `analyst.py` | System prompt, directive protocol, per-directive execution |
| `engine.py` | The bounded run loop, shared by CLI and server |
| `server.py` | FastAPI app + JSON API |
| `cli.py` | `check`, `introspect`, `ask`, `serve` |

## The read-only contract (defense in depth)

1. A read-only database role (your strongest guarantee; you create it).
2. SQL validation: a single SELECT/WITH, with a write/DDL keyword denylist.
3. A read-only database session (`SET TRANSACTION READ ONLY`) and a statement
   timeout.
4. HTTP: GET only, plus a positive per-source allowlist for APIs that expose
   writes over GET.
5. A write-request firewall that refuses any user request to change data before
   it reaches an executor.

The only output Querion produces is the answer. It writes nothing, anywhere.

## Why the Claude Code CLI

No API key to manage, and the model runs under your existing Claude Code
authentication. Querion calls it with all tools disabled and zero MCP servers,
so the model is a pure reasoning engine over the context Querion assembles.
Opus is recommended because the analyst reasons multi-step over your schema and
API docs, and the quality difference is real.
