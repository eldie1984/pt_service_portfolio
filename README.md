# Portfolio Management Service

REST API for managing investment portfolios, holdings, instruments, and exchanges. Part of the Portfolio Tracker platform.

- **Runtime**: Python 3.14 / FastAPI
- **Port**: `3002`
- **Database**: PostgreSQL (schema `portfolio_service`)
- **Auth**: JWT (Bearer token)

## Getting started

### Prerequisites

- Python 3.14+
- [Poetry](https://python-poetry.org/)
- PostgreSQL instance with the `portfolio_service` schema

### Install & run

```bash
poetry install
cp .env.example .env   # edit values before running
poetry run python main.py
```

The server starts at `http://localhost:3002`.

### Environment variables

| Variable | Default | Required |
|---|---|---|
| `PORT` | `3002` | No |
| `DEBUG` | `false` | No |
| `DATABASE_URL` | `postgresql://postgres:password@localhost:5432/portfolio_tracker` | **Yes** |
| `SECRET_KEY` | *(insecure placeholder)* | **Yes in production** |
| `ALGORITHM` | `HS256` | No |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | No |

### Docker

```bash
docker build -t portfolio-service .
docker run -p 3002:3002 \
  -e DATABASE_URL="postgresql://user:pass@host:5432/portfolio_tracker" \
  -e SECRET_KEY="your-secret" \
  portfolio-service
```

## API overview

All endpoints (except `/health` and `/metrics`) require a JWT Bearer token in the `Authorization` header.

Interactive docs are available at:
- **Swagger UI** → `http://localhost:3002/docs`
- **ReDoc** → `http://localhost:3002/redoc`
- **OpenAPI JSON** → `http://localhost:3002/openapi.json`

### Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |
| GET | `/portfolios` | List portfolios for current user |
| POST | `/portfolios` | Create portfolio |
| GET | `/portfolios/{id}` | Get portfolio with holdings |
| GET | `/portfolios/{id}/performance` | Get performance summary |
| GET | `/instruments` | List all instruments |
| POST | `/instruments` | Create instrument |
| GET | `/instruments/{id}` | Get instrument by ID |
| GET | `/instruments/symbol/{symbol}` | Get instrument by symbol |
| GET | `/exchanges` | List active exchanges |
| POST | `/exchanges` | Create exchange |

### Error format

All error responses follow a consistent envelope:

```json
{
  "error": "Human-readable message",
  "status": 404,
  "path": "/portfolios/99",
  "timestamp": 1715000000.0
}
```

## Development

```bash
# Run tests
poetry run pytest

# Run tests with coverage (80% minimum)
poetry run pytest --cov=app --cov-report=term-missing

# Lint & format
poetry run ruff check app/
poetry run black app/
poetry run isort app/

# Type checking
poetry run mypy app/

# Security scan
poetry run bandit -r app/
```

## Database schema

Tables live in the `portfolio_service` PostgreSQL schema:

- **portfolios** — user portfolios (`id`, `user_id`, `name`, `description`, `created_at`, `updated_at`)
- **holdings** — positions within a portfolio (`id`, `portfolio_id`, `instrument_id`, `quantity`, `average_cost`, `market_value`, `unrealized_pnl`)
- **instruments** — tradeable assets (`id`, `symbol`, `name`, `type`, `exchange`, `currency`)
- **exchanges** — trading venues (`id`, `name`, `type`, `country`, `code`, `is_active`)

## Observability

Prometheus metrics are exposed at `GET /metrics`:

| Metric | Type | Description |
|---|---|---|
| `portfolio_http_requests_total` | Counter | HTTP requests by method, endpoint, status |
| `portfolio_http_request_duration_seconds` | Histogram | Request latency |
| `portfolio_active_connections` | Gauge | Concurrent in-flight requests |
| `portfolio_operations_total` | Counter | Business operations by name and status |
| `portfolio_database_connections` | Gauge | DB connection pool usage |
| `portfolio_holdings_count` | Gauge | Total holdings across all portfolios |
| `portfolio_total_value_usd` | Gauge | Portfolio value per portfolio ID |
