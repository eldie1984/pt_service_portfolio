from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging
from jose import JWTError, jwt

from app.database.connection import get_db, Database
from app.metrics import record_portfolio_operation

router = APIRouter()
logger = logging.getLogger(__name__)

# Pydantic models
class PortfolioCreate(BaseModel):
    name: str
    description: Optional[str] = None

class PortfolioResponse(BaseModel):
    id: int
    user_id: str
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

class Holding(BaseModel):
    id: int
    portfolio_id: int
    instrument_id: int
    quantity: float
    average_cost: float
    market_value: float
    unrealized_pnl: float
    symbol: str
    instrument_name: str
    instrument_type: str
    exchange: str
    currency: str

class PortfolioWithHoldings(BaseModel):
    id: int
    user_id: str
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    holdings: List[Holding]

class PerformanceSummary(BaseModel):
    portfolioId: int
    totalHoldings: int
    totalMarketValue: float
    totalUnrealizedPnL: float
    totalReturn: float

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate JWT token and extract user info"""
    try:
        from app.config import settings
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return {"id": "550e8400-e29b-41d4-a716-446655440000", "username": email, "email": email}
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

def get_user_from_request(request: Request) -> str:
    """Extract user ID from request headers (for backward compatibility)"""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
    return user_id

@router.get("/", response_model=List[PortfolioResponse])
async def get_portfolios(current_user: dict = Depends(get_current_user)):
    """Get all portfolios for a user"""
    try:
        user_id = current_user["id"]
        
        async with await Database.get_connection() as connection:
            result = await connection.fetch(
                'SELECT * FROM portfolio_service.portfolios WHERE user_id = $1 ORDER BY created_at DESC',
                user_id
            )
        
        record_portfolio_operation("list_portfolios", "success")
        return [dict(row) for row in result]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolios: {e}")
        record_portfolio_operation("list_portfolios", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve portfolios")

@router.post("/", response_model=PortfolioResponse, status_code=201)
async def create_portfolio(
    portfolio: PortfolioCreate, 
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Create new portfolio"""
    try:
        user_id = current_user["id"]
        
        result = await db.fetchrow(
            """INSERT INTO portfolio_service.portfolios (user_id, name, description) 
               VALUES ($1, $2, $3) RETURNING *""",
            user_id, portfolio.name, portfolio.description
        )
        
        record_portfolio_operation("create_portfolio", "success")
        return dict(result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating portfolio: {e}")
        record_portfolio_operation("create_portfolio", "error")
        raise HTTPException(status_code=500, detail="Failed to create portfolio")

@router.get("/{portfolio_id}", response_model=PortfolioWithHoldings)
async def get_portfolio(portfolio_id: int, current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Get portfolio with holdings"""
    try:
        user_id = current_user["id"]
        
        # Get portfolio details
        portfolio_result = await db.fetchrow(
            'SELECT * FROM portfolio_service.portfolios WHERE id = $1 AND user_id = $2',
            portfolio_id, user_id
        )
        
        if not portfolio_result:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        # Get holdings with instrument details
        holdings_result = await db.fetch(
            """SELECT h.*, i.symbol, i.name as instrument_name, i.type, i.exchange, i.currency
               FROM portfolio_service.holdings h
               JOIN portfolio_service.instruments i ON h.instrument_id = i.id
               WHERE h.portfolio_id = $1""",
            portfolio_id
        )
        
        portfolio_data = dict(portfolio_result)
        portfolio_data["holdings"] = [dict(row) for row in holdings_result]
        
        record_portfolio_operation("get_portfolio", "success")
        return portfolio_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio: {e}")
        record_portfolio_operation("get_portfolio", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve portfolio")

@router.get("/{portfolio_id}/performance", response_model=PerformanceSummary)
async def get_portfolio_performance(portfolio_id: int, current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Get portfolio performance summary"""
    try:
        user_id = current_user["id"]
        
        # Verify portfolio ownership
        portfolio_result = await db.fetchrow(
            'SELECT * FROM portfolio_service.portfolios WHERE id = $1 AND user_id = $2',
            portfolio_id, user_id
        )
        
        if not portfolio_result:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        # Get performance metrics
        performance_result = await db.fetchrow(
            """SELECT 
               COUNT(*) as total_holdings,
               COALESCE(SUM(market_value), 0) as total_market_value,
               COALESCE(SUM(unrealized_pnl), 0) as total_unrealized_pnl
             FROM portfolio_service.holdings 
             WHERE portfolio_id = $1""",
            portfolio_id
        )
        
        performance = dict(performance_result)
        total_market_value = float(performance["total_market_value"])
        total_unrealized_pnl = float(performance["total_unrealized_pnl"])
        
        performance_summary = PerformanceSummary(
            portfolioId=portfolio_id,
            totalHoldings=int(performance["total_holdings"]),
            totalMarketValue=total_market_value,
            totalUnrealizedPnL=total_unrealized_pnl,
            totalReturn=(total_unrealized_pnl / total_market_value * 100) if total_market_value > 0 else 0
        )
        
        record_portfolio_operation("get_performance", "success")
        return performance_summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio performance: {e}")
        record_portfolio_operation("get_performance", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve performance metrics")
