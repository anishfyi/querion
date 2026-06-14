# Configuration

Everything Querion needs is in one `querion.yaml` plus environment variables for
secrets. Start from `querion.example.yaml`.

## The shape

```yaml
company: "Acme Inc"
model: opus
database:
  dsn: ${QUERION_DATABASE_DSN}
  statement_timeout_ms: 15000
  row_cap: 500
  schema_doc: docs/schema.md   # optional; else live introspection
sources:
  - name: stripe
    base_url: https://api.stripe.com
    auth_header: "Authorization: Bearer ${STRIPE_KEY}"
    safe_get: [ "^/v1/charges", "^/v1/customers" ]
    docs: docs/sources/stripe.md
limits:
  daily_per_user: 50
  max_steps: 7
  max_directives_per_step: 4
trove:
  enabled: false
  layer_path: .trove/semantic.md
```

## Database

- `dsn` is a standard Postgres connection string. Point it at a READ-ONLY role.
  Creating one is two statements:

  ```sql
  CREATE ROLE querion_ro LOGIN PASSWORD 'choose-a-strong-one';
  GRANT CONNECT ON DATABASE yourdb TO querion_ro;
  GRANT USAGE ON SCHEMA public TO querion_ro;
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO querion_ro;
  ALTER ROLE querion_ro SET default_transaction_read_only = on;
  ALTER ROLE querion_ro SET statement_timeout = '15s';
  -- Then REVOKE SELECT on any tables holding secrets (sessions, raw tokens...).
  ```

- `schema_doc` is optional. With it, Querion uses your curated description (best
  for big or subtle schemas). Without it, `querion introspect` style live
  introspection runs at startup. Generate a starting point with:

  ```bash
  querion introspect -o docs/schema.md
  ```

## Sources (any HTTP API)

One block per platform. Add the secret to the environment, reference it in
`auth_header`, and describe the read endpoints in `docs`.

`safe_get` is a list of regular expressions matched against the start of the
request path. If present, ONLY matching paths are allowed (default-deny). Use it
whenever an API exposes state-changing operations over GET (many do). If the API
is strictly RESTful, you may omit it and any GET is allowed.

## Limits

- `daily_per_user`: per-caller daily question cap (0 = unlimited). On the web the
  caller key is `X-Querion-User` if set, else the client IP.
- `max_steps`: reasoning steps per question.
- `max_directives_per_step`: independent reads batched into one step.

## Model

`model` is a Claude Code CLI alias (for example `opus`). Opus is recommended.
Set `claude_bin` only if `claude` is not on PATH.
