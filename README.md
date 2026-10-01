<p align="center">
  <a href="https://velofy.co/querion/"><picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/anishfyi/querion/main/assets/tile-dark.svg">
    <img alt="Querion" src="https://raw.githubusercontent.com/anishfyi/querion/main/assets/tile-light.svg" width="360">
  </picture></a>
</p>

# Querion

A strictly read-only, natural-language data analyst. Point it at a Postgres database and read-only APIs, then ask questions in plain English. It runs on your locally authenticated Claude Code CLI, so there is no API key to manage.

**Documentation: https://velofy.co/querion/**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)

Querion answers like a senior data analyst: the number, the insight, the exact query behind it, and a chart when one helps. It is built to only read.

```text
"new vs returning customers this month, with a chart"
   -> Querion plans read-only steps
   -> runs SELECTs on Postgres and GETs on your APIs
   -> replies with the number, a table, a chart, and the SQL it used
```

## Install

Requirements: Python 3.9+, a Postgres database, and the [Claude Code CLI](https://docs.claude.com/en/docs/claude-code) installed and logged in on the host (run `claude` once).

```bash
git clone https://github.com/anishfyi/querion.git
cd querion
pip install -e ".[all]"      # core + web UI + charts + .env loading
```

## Minimal example

```bash
cp querion.example.yaml querion.yaml
cp .env.example .env         # set QUERION_DATABASE_DSN to a READ-ONLY role
querion check                # validates config, database, and the claude CLI
querion ask "how many orders were placed in the last 7 days?"
querion serve                # web UI at http://127.0.0.1:8000
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

## Features

- **Read-only checks.** SQL must be a single SELECT or WITH statement, HTTP is GET only with an optional per-source allowlist, and explicit write statements in a question are refused. Details and limits are in the [safety model](https://velofy.co/querion/safety-model/).
- **Multi-source.** Joins history in Postgres with live data from your APIs in one answer.
- **Transparent.** Every answer shows the SQL that produced it.
- **No API key.** Uses the Claude Code CLI you already have. Opus is recommended.
- **Web UI and JSON API.** `querion serve` starts a FastAPI app. It has no built-in login, so put it behind your own authentication.
- **Optional semantic layer.** Reads a layer maintained by [Trove](https://github.com/anishfyi/trove) when `trove.enabled` is true.

## Add an API source

Adding a platform is configuration, not code. Put the secret in `.env`, describe the read endpoints in a markdown file (see [docs/sources/example.md](docs/sources/example.md)), and add a block:

```yaml
sources:
  - name: stripe
    base_url: https://api.stripe.com
    auth_header: "Authorization: Bearer ${STRIPE_KEY}"
    safe_get:                     # only these read paths are allowed
      - ^/v1/charges
      - ^/v1/customers
    docs: docs/sources/stripe.md
```

A GET is not always read-only, so set `safe_get` for any API that is not strictly RESTful. See [Connecting data sources](https://velofy.co/querion/data-sources/).

## Read-only by design, with limits

The strongest guarantee is a read-only Postgres role and read-only API tokens. Querion adds application checks on top: SQL validation, a read-only database session with a statement timeout, GET-only HTTP, and a write-request firewall. The firewall deterministically catches pasted SQL write statements and GraphQL mutations. Plain-English write requests rely on the model following its instructions, with the other layers as the backstop. Read [the safety model](https://velofy.co/querion/safety-model/) for exactly what is enforced.

## Documentation

- [Overview](https://velofy.co/querion/)
- [Installation](https://velofy.co/querion/installation/)
- [Quickstart](https://velofy.co/querion/quickstart/)
- [Configuration reference](https://velofy.co/querion/configuration/)
- [Connecting data sources](https://velofy.co/querion/data-sources/)
- [Safety model](https://velofy.co/querion/safety-model/)
- [Architecture](https://velofy.co/querion/architecture/)
- [Usage examples](https://velofy.co/querion/examples/)
- [CLI and web API](https://velofy.co/querion/cli-and-api/)
- [Project status](https://velofy.co/querion/status/)

## Contributing

Issues and pull requests are welcome on GitHub. Open an issue first for larger changes.

## License

MIT. See [LICENSE](LICENSE). Companion project: [Trove](https://github.com/anishfyi/trove).
