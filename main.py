from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uvicorn
import os
from datetime import datetime
from contextlib import asynccontextmanager

from app.config import settings
from app.database import init_db
from app.routers import portfolio, instruments, exchanges,brokers
from app.middleware.error_handler import setup_error_handlers
from app.metrics import MetricsMiddleware, metrics_endpoint

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown
    from app.database.connection import Database
    await Database.disconnect()

app = FastAPI(
    title="Portfolio Management Service",
    description="""
REST API for managing investment portfolios, holdings, instruments, and exchanges.

## Authentication

All endpoints (except `/health` and `/metrics`) require a **JWT Bearer token**:

```
Authorization: Bearer <token>
```

## Error responses

All errors return a consistent envelope:

```json
{
  "error": "Human-readable message",
  "status": 404,
  "path": "/portfolios/99",
  "timestamp": 1715000000.0
}
```

## Rate limiting

`/health` is limited to **60 requests/minute** per IP. Business endpoints inherit
the global rate limiter configured via `RATE_LIMIT_PER_MINUTE`.
""",
    version="2.0.0",
    contact={
        "name": "Diego Gasch",
        "email": "eldie1984@gmail.com",
    },
    license_info={
        "name": "Private",
    },
    openapi_tags=[
        {
            "name": "Health",
            "description": "Service liveness and readiness checks.",
        },
        {
            "name": "Metrics",
            "description": "Prometheus-compatible metrics endpoint.",
        },
        {
            "name": "Portfolios",
            "description": "Create and manage investment portfolios and view performance summaries.",
        },
        {
            "name": "Instruments",
            "description": "Manage tradeable instruments (stocks, ETFs, crypto, etc.).",
        },
        {
            "name": "Exchanges",
            "description": "Manage trading venues and exchanges.",
        },
    ],
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security middleware
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["*"]  # Configure based on your environment
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure based on your environment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup error handlers
setup_error_handlers(app)

# Add metrics middleware
app.add_middleware(MetricsMiddleware)

# Health check
@app.get("/health", tags=["Health"])
@limiter.limit("60/minute")
async def health_check(request: Request):
    return {
        "status": "ok",
        "service": "portfolio-service",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0"
    }

@app.get("/metrics", tags=["Metrics"])
async def metrics():
    """Prometheus metrics endpoint"""
    return await metrics_endpoint()

# Include routers
app.include_router(portfolio.router, prefix="/portfolios", tags=["Portfolios"])
app.include_router(instruments.router, prefix="/instruments", tags=["Instruments"])
app.include_router(exchanges.router, prefix="/exchanges", tags=["Exchanges"])
app.include_router(brokers.router, prefix="/brokers", tags=["Brokers"])

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
