from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
import time
import logging

logger = logging.getLogger(__name__)

# Metrics
REQUEST_COUNT = Counter(
    'portfolio_http_requests_total',
    'Total HTTP requests for portfolio service',
    ['method', 'endpoint', 'status_code']
)

REQUEST_DURATION = Histogram(
    'portfolio_http_request_duration_seconds',
    'HTTP request duration in seconds for portfolio service',
    ['method', 'endpoint']
)

ACTIVE_CONNECTIONS = Gauge(
    'portfolio_active_connections',
    'Number of active connections for portfolio service'
)

PORTFOLIO_OPERATIONS = Counter(
    'portfolio_operations_total',
    'Total number of portfolio operations',
    ['operation', 'status']
)

DATABASE_CONNECTIONS = Gauge(
    'portfolio_database_connections',
    'Number of active database connections'
)

HOLDINGS_COUNT = Gauge(
    'portfolio_holdings_count',
    'Total number of holdings across all portfolios'
)

PORTFOLIO_VALUE = Gauge(
    'portfolio_total_value_usd',
    'Total portfolio value in USD',
    ['portfolio_id']
)

class MetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            start_time = time.time()
            
            # Increment active connections
            ACTIVE_CONNECTIONS.inc()
            
            # Store original send
            original_send = send
            
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    method = scope["method"]
                    endpoint = scope["path"]
                    
                    # Record metrics
                    REQUEST_COUNT.labels(
                        method=method,
                        endpoint=endpoint,
                        status_code=status_code
                    ).inc()
                    
                    # Record duration
                    duration = time.time() - start_time
                    REQUEST_DURATION.labels(
                        method=method,
                        endpoint=endpoint
                    ).observe(duration)
                
                await original_send(message)
            
            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                # Decrement active connections
                ACTIVE_CONNECTIONS.dec()
        else:
            await self.app(scope, receive, send)

def record_portfolio_operation(operation: str, status: str):
    """Record portfolio operation metrics"""
    PORTFOLIO_OPERATIONS.labels(operation=operation, status=status).inc()

def update_database_connections(count: int):
    """Update database connection count"""
    DATABASE_CONNECTIONS.set(count)

def update_holdings_count(count: int):
    """Update holdings count"""
    HOLDINGS_COUNT.set(count)

def update_portfolio_value(portfolio_id: str, value: float):
    """Update portfolio value"""
    PORTFOLIO_VALUE.labels(portfolio_id=portfolio_id).set(value)

async def metrics_endpoint():
    """Prometheus metrics endpoint"""
    try:
        metrics_data = generate_latest()
        return Response(
            content=metrics_data,
            media_type=CONTENT_TYPE_LATEST
        )
    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        return Response(
            content="Error generating metrics",
            status_code=500
        )
