# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
poetry install

# Run development server (port 3002)
poetry run python main.py
# or with reload
poetry run uvicorn main:app --reload --port 3002

# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=app --cov-report=term-missing

# Run a single test file
poetry run pytest tests/test_portfolio.py -v

# Lint / format
poetry run ruff check app/
poetry run black app/
poetry run isort app/

# Type checking
poetry run mypy app/

# Security scan
poetry run bandit -r app/
```

## Architecture

This is a **FastAPI microservice** for portfolio management, part of a larger Portfolio Tracker system. It runs on port `3002`.

### Request flow

```
HTTP Request
  → Rate limiter (slowapi, 60 req/min)
  → MetricsMiddleware (Prometheus counters/histograms)
  → CORS / TrustedHost middleware
  → Router (portfolios / instruments / exchanges)
    → JWT auth via get_current_user() (python-jose)
    → asyncpg connection pool (Database singleton)
    → PostgreSQL (schema: portfolio_service)
```

### Key design notes

- **Database access**: `Database` is a class-level singleton in `app/database/connection.py`. `get_db()` returns the pool directly (not a connection). Routers using `get_db` call `db.fetchrow()` / `db.fetch()` directly on the pool, while some routers use `async with db.acquire() as connection:` — both patterns exist and are valid.
- **Auth**: JWT tokens are decoded per-request in `get_current_user()`, duplicated in both `portfolio.py` and `instruments.py` routers. The user ID returned is currently a hardcoded UUID placeholder — real user lookup is not yet implemented.
- **Metrics**: Prometheus metrics are exposed at `GET /metrics`. All operations call `record_portfolio_operation(operation, status)` from `app/metrics.py`.
- **Error format**: All errors return `{ error, status, path, timestamp }` — enforced by handlers in `app/middleware/error_handler.py`.
- **DB schema**: All tables live in the `portfolio_service` PostgreSQL schema: `portfolios`, `holdings`, `instruments`, `exchanges`.

### Environment variables (via `.env`)

| Variable | Default | Description |
|---|---|---|
| `PORT` | `3002` | Server port |
| `DEBUG` | `false` | Enable uvicorn reload |
| `DATABASE_URL` | `postgresql://postgres:password@localhost:5432/portfolio_tracker` | asyncpg connection string |
| `SECRET_KEY` | *(insecure default)* | JWT signing key — **must override in production** |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | JWT expiry |
