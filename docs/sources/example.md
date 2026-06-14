# Example source API docs

This file is what you drop in for each platform. Querion injects it into the
analyst's context, so write it the way you would brief a new analyst: what the
API is, which read endpoints exist, and what each returns. Keep it to read
endpoints only.

## What this API is

The Example platform stores customers, orders, and invoices. It is the live
source of truth for current status; the Postgres mirror may lag.

## Auth

Sent automatically by Querion from `auth_header` in querion.yaml. You do not
need to mention the key here.

## Read endpoints (GET only)

| Endpoint | Purpose |
|---|---|
| `GET /v1/customers?limit=50` | List customers (paginated) |
| `GET /v1/customers/{id}` | One customer record |
| `GET /v1/orders?status=open&limit=50` | List orders by status |
| `GET /v1/orders/{id}` | One order, with line items |
| `GET /v1/invoices?customer={id}` | Invoices for a customer |

## Notes and gotchas

- Amounts are in minor units (pence/cents); divide by 100 for display.
- `status` values: `open`, `paid`, `void`, `refunded`.
- Pagination uses `?limit=` and `?starting_after=`; max limit is 100.
- This API is RESTful: GET is always read-only here. If your platform exposes
  state-changing operations over GET, list ONLY the safe read paths in
  `safe_get` so Querion can never reach the others.
