# Querion

**A strictly read-only, natural-language data analyst that plugs into any platform and runs on the Claude Code CLI.**

Point Querion at your Postgres database and your read-only APIs, then ask questions in plain English. It answers like a senior data analyst: the number, the insight, the exact query behind it, and a chart when one helps. It never writes anything, anywhere.

There is no API key to manage. Querion uses your locally authenticated Claude Code CLI as its brain.

```
"new vs returning customers this month, with a chart"
   -> Querion plans read-only steps
   -> runs SELECTs on Postgres and GETs on your APIs
   -> replies: headline number, a table, a chart, and the SQL it used
```

---

## Why Querion

Most teams have the data but not the analyst time. Dashboards answer the questions you anticipated; everything else becomes a ticket. Querion turns the long tail of "can someone just pull..." into a chat message, while staying safe enough to point at production:

- **Read-only by contract.** SELECT and WITH only, GET only with a per-source allowlist, and a firewall that refuses any request to change data. See [the safety model](#the-read-only-contract).
- **Platform agnostic.** Add a key and secret to the environment, drop in the API docs, connect Postgres. No code. It works for any company and any stack.
- **Multi-source.** It joins history in Postgres with live truth from your APIs in a single answer, picking the right source per question.
- **Transparent.** Every number comes with the query that produced it, so you can trust it and reuse it.
- **No keys, no lock-in.** It runs on the Claude Code CLI you already have, with Opus recommended for the deepest reasoning.

---

## How it works

Querion is a small read-only loop around the Claude Code CLI. The brain never executes anything itself; it can only emit fenced, read-only directives that the runner validates and runs.

```
question
  -> write-request firewall (refuses any "change my data" request)
  -> the brain emits read-only directives:
        run-sql      a single SELECT / WITH against Postgres
        source:NAME  a GET against a configured HTTP API
        chart        a chart spec from data already fetched
  -> the runner executes them read-only and feeds results back
  -> repeat until the brain returns a final answer (no execute fence)
```

Steps are stateless (the full transcript is passed each turn), so nothing leaks across users. Full details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Quickstart

### 1. Install

```bash
git clone https://github.com/anishfyi/querion.git
cd querion
pip install -e ".[all]"      # core + web UI + charts + .env loading
```

You also need the Claude Code CLI installed and logged in once:

```bash
# install Claude Code, then:
claude            # log in (browser OAuth / your subscription) once
```

### 2. Configure

```bash
cp querion.example.yaml querion.yaml
cp .env.example .env
# edit .env with your read-only Postgres DSN and any API keys
# edit querion.yaml: company name, sources, limits
```

A minimal `querion.yaml`:

```yaml
company: "Acme Inc"
model: opus
database:
  dsn: ${QUERION_DATABASE_DSN}     # a READ-ONLY Postgres role
sources: []                         # add platforms here later
limits:
  daily_per_user: 50
```

### 3. Check and run

```bash
querion check                       # validates config, DB, and the claude CLI
querion ask "how many orders were placed in the last 7 days?"
querion serve                       # web UI at http://127.0.0.1:8000
```

That is the whole loop: connect a database, ask a question.

---

## Integrate any platform

Adding a platform is configuration, not code. Three things:

1. **Add the secret to the environment** (`.env` or your secret manager):

   ```bash
   STRIPE_KEY=sk_live_xxx
   ```

2. **Describe the API** in a markdown file (see [docs/sources/example.md](docs/sources/example.md) for the shape). List the read endpoints and what they return, the way you would brief a new analyst.

3. **Add a source block** to `querion.yaml`:

   ```yaml
   sources:
     - name: stripe
       base_url: https://api.stripe.com
       auth_header: "Authorization: Bearer ${STRIPE_KEY}"
       safe_get:                     # only these read paths are allowed
         - ^/v1/charges
         - ^/v1/customers
         - ^/v1/invoices
       docs: docs/sources/stripe.md
   ```

Now Querion can answer questions that span Postgres and Stripe together. Repeat the block for every platform (your billing provider, your 3PL, your CRM, your warehouse system, and so on).

> **A note on `safe_get`.** A GET is not automatically side-effect free. Some real APIs expose state-changing operations over GET. When `safe_get` is set, only matching paths are allowed (default-deny), so Querion can never reach the destructive ones. Set it for any API that is not strictly RESTful. This is a hard-won default.

---

## The read-only contract

Querion is built so that "it never writes" is true by construction, with defense in depth:

1. **A read-only database role.** Your strongest guarantee. You create it (two minutes, recipe in [docs/CONFIGURATION.md](docs/CONFIGURATION.md)).
2. **SQL validation.** A single SELECT or WITH statement only, with a write and DDL keyword denylist that also catches data-modifying CTEs.
3. **A read-only database session** plus a server-side statement timeout.
4. **HTTP egress is GET only**, with a positive per-source allowlist for APIs that expose writes over GET.
5. **A write-request firewall.** If a user asks Querion to insert, update, delete, cancel, create, or sync anything, the request is refused before it reaches any executor. Asking about past changes ("which orders were cancelled last week?") is normal analytics and is answered.

The only thing Querion ever produces is the answer.

---

## Suggested configuration

Querion runs anywhere Python and the Claude Code CLI run, but this is the setup it is tuned for:

- **AWS (EC2)** for a stable, always-on host. A small instance is plenty; the heavy lifting is the model, not the box. Run `querion serve` under a process manager (systemd or supervisor) and put it behind your load balancer or a reverse proxy.
- **Claude Code CLI** as the brain, authenticated once on the host. No API key to rotate, and the model runs under your existing Claude Code plan.
- **Opus** as the model (`model: opus`). The analyst reasons multi-step over your schema and API docs; Opus is the recommended tier for that depth and is what Querion is designed around.

In short: **AWS + Claude Code CLI + Opus** is the recommended way to run Querion in production.

---

## Semantic layer with Trove

Querion is far smarter when it knows your domain: what "active customer" means, which table is the source of truth, how your metrics are defined. You can hand-write that, or let [**Trove**](https://github.com/anishfyi/trove) build and maintain it for you.

Trove is a companion project that builds and maintains a file-based semantic layer as you work, and reloads it every session. Enable it in `querion.yaml` and Querion folds that layer into its knowledge automatically:

```yaml
trove:
  enabled: true
  layer_path: .trove/semantic.md
```

So your semantic layer stays current on its own, and every Querion answer speaks your business language. Trove lives at [github.com/anishfyi/trove](https://github.com/anishfyi/trove).

---

## CLI

```
querion check                  validate config, test the database and the claude CLI
querion introspect [-o FILE]   write a schema markdown from the live database (read-only)
querion ask "question"         answer one question in the terminal
querion serve [--host --port]  run the web app and JSON API
```

Global flags: `-c/--config PATH` to point at a specific `querion.yaml`.

---

## Web UI and API

`querion serve` starts a FastAPI app with a single-page Alpine.js UI: an ask box with live step-by-step progress, interactive charts, and the SQL behind every answer, plus a showcase of what Querion can do.

JSON API:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/config` | Safe metadata for the UI (company, model, source names) |
| GET | `/api/health` | Liveness plus dependency checks |
| POST | `/api/ask` | Start a question; returns a run id |
| GET | `/api/ask/{id}` | Poll a run (steps, answer, charts, SQL) |

The web caller identity for the daily cap is the `X-Querion-User` header if present, else the client IP. Put `querion serve` behind your own auth (SSO, a reverse proxy, an IP allowlist) before exposing it; the dashboard has no built-in login.

---

## Project layout

```
querion/
  config.py      load querion.yaml + env interpolation
  llm.py         Claude Code CLI wrapper
  safety.py      SQL validation, HTTP allowlist, write firewall
  db.py          read-only Postgres
  sources.py     generic read-only HTTP connectors
  knowledge.py   schema + API docs + Trove semantic layer
  charts.py      colored charts with a unicode fallback
  limits.py      per-user daily cap
  analyst.py     system prompt + directive protocol
  engine.py      the read-only run loop
  server.py      FastAPI app + API
  cli.py         command line
  web/index.html the Alpine.js UI
docs/            ARCHITECTURE.md, CONFIGURATION.md, sources/
```

---

## Requirements

- Python 3.9+
- A Postgres database (a read-only role is strongly recommended)
- The Claude Code CLI, authenticated on the host
- Optional: `matplotlib` for image charts (a unicode chart works without it)

---

## License

MIT. See [LICENSE](LICENSE).

---

Querion is a read-only data analyst. Pair it with [Trove](https://github.com/anishfyi/trove) for an always-current semantic layer.
