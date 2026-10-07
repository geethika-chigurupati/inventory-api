# inventory-api

![CI](https://github.com/geethika-chigurupati/inventory-api/actions/workflows/ci.yml/badge.svg)

A FastAPI inventory service with **JWT authentication, role-based access control (RBAC),
PostgreSQL storage, and Redis caching**. Products have a stock count; different roles can
read, adjust stock, or manage the catalog.

## Roles and endpoints

| Endpoint | viewer | staff | admin |
|---|:-:|:-:|:-:|
| `POST /auth/login` | public | public | public |
| `GET /products`, `GET /products/{id}` | yes | yes | yes |
| `PATCH /products/{id}/stock` | no | yes | yes |
| `POST /products`, `DELETE /products/{id}` | no | no | yes |
| `POST /users` | no | no | yes |

Roles are ordered `viewer < staff < admin`; each endpoint names the minimum role it needs.
Interactive API docs are served at `/docs`.

## Design decisions

- **Role lookup from the database, not the token.** The token only identifies the user. The role
  is read from the database on each request, so a changed role or a deleted user takes effect
  immediately instead of at token expiry.
- **Pinned JWT algorithm.** Tokens are HS256, the server fixes the algorithm (the token header
  cannot choose it, which blocks `alg: none` tricks), and `exp`, `sub`, and `iss` are required.
- **Password hashing** uses scrypt from the standard library with a per-password salt and a
  constant-time comparison. Login for an unknown username still does a hash check, so response
  time does not reveal which usernames exist.
- **Atomic stock updates.** Changing stock is one `UPDATE ... WHERE stock + delta >= 0`
  statement, so two simultaneous requests cannot both pass a check and oversell. A database
  `CHECK` constraint backs this up.
- **Cache-aside with Redis.** Single products and product lists are cached for a short TTL.
  Writes delete the product key and bump a version number that is part of every list key, which
  invalidates all cached list pages in one step without scanning keys.
- **The cache fails open.** If Redis is unreachable, requests fall back to PostgreSQL and a
  warning is logged. A Redis outage slows the API down but does not break it.
- **Fail closed on configuration.** The app refuses to start without a `JWT_SECRET` of at least
  32 characters.

## Quickstart

Requires Python 3.11+ and Docker.

```bash
docker compose up -d                       # PostgreSQL + Redis
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

export DATABASE_URL="postgresql+psycopg://inventory:inventory@localhost:5432/inventory"
export REDIS_URL="redis://localhost:6379/0"
export JWT_SECRET="replace-with-a-random-string-of-at-least-32-characters"
export ADMIN_USERNAME=admin ADMIN_PASSWORD="replace-with-a-strong-password"

uvicorn inventory_api.main:create_app --factory --port 8000
```

On first start with an empty database, the admin user is created from `ADMIN_USERNAME` and
`ADMIN_PASSWORD`. Then:

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"username":"admin","password":"replace-with-a-strong-password"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -X POST localhost:8000/products -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"sku":"DEMO-1","name":"Demo","price":"4.50","stock":2}'

curl localhost:8000/products -H "authorization: Bearer $TOKEN"
```

See `.env.example` for all settings.

## Testing

```bash
pytest -q        # unit tests: SQLite + an in-memory fake Redis, no services needed
```

- The unit tests cover password and token handling, login, role checks on every endpoint,
  validation, pagination, cache hits, cache invalidation, and the fail-open behaviour with a
  broken Redis.
- Integration tests run against **real PostgreSQL and Redis** when `TEST_DATABASE_URL` and
  `TEST_REDIS_URL` are set (CI sets them using service containers). They include a concurrency
  test: 30 simultaneous requests to remove one unit from a product with 10 in stock result in
  exactly 10 successes and 20 conflicts, and the final stock is 0.

## Limitations

- Tables are created at startup with `create_all`; there are no database migrations yet.
- No refresh tokens, token revocation list, or login rate limiting.
- After a Redis outage, cached entries written before the outage can stay stale for up to the
  cache TTL (60 seconds by default).
- HS256 uses one shared secret; there is no key rotation.

## Roadmap

- [ ] Alembic migrations
- [ ] Dockerfile for the API and a full `docker compose` stack
- [ ] Rate limiting on `/auth/login`
- [ ] Prometheus metrics (request latency, cache hit rate)
- [ ] Load test with Locust or k6, with measured results published here

## License

MIT
