from locale import currency
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime,timezone
import logging
from jose import JWTError, jwt
import uuid


from app.database import get_db_conn
from app.metrics import record_portfolio_operation
from .utils import get_current_user,get_user_from_request

router = APIRouter()
logger = logging.getLogger(__name__)

# Pydantic models
class PortfolioCreate(BaseModel):
    name: str
    description: Optional[str] = None

class PortfolioResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    currency: Optional[str]

class Holding(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    instrument_id: uuid.UUID
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
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    holdings: List[Holding]

class PerformanceSummary(BaseModel):
    portfolioId: uuid.UUID
    totalHoldings: int
    totalMarketValue: float
    totalUnrealizedPnL: float
    totalReturn: float


class PortfolioSignals(BaseModel):
    id: str
    symbol: str
    action: str
    confidence: float
    time: datetime

security = HTTPBearer()




@router.get(
    "/",
    response_model=List[PortfolioResponse],
    summary="List portfolios",
    response_description="Portfolios owned by the authenticated user, ordered by creation date descending.",
)
async def get_portfolios(current_user: dict = Depends(get_current_user), 
    db = Depends(get_db_conn)):
    """Return all portfolios that belong to the authenticated user."""
    try:
        user_id = str(current_user["id"])

        result = await db.fetch(
                'SELECT cast(id as text) as id, cast(user_id as text) as user_id, name, description , created_at, updated_at,currency FROM portfolio_service.portfolios WHERE user_id = $1 ORDER BY created_at DESC',
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

@router.post(
    "/",
    response_model=PortfolioResponse,
    status_code=201,
    summary="Create portfolio",
    response_description="The newly created portfolio.",
)
async def create_portfolio(
    portfolio: PortfolioCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db_conn)
):
    """Create a new portfolio for the authenticated user."""
    try:
        user_id = str(current_user["id"])
        
        # Insert portfolio
        result = await db.fetchrow(
            """INSERT INTO portfolio_service.portfolios 
               (name, description, user_id, created_at, updated_at) 
               VALUES ($1, $2, $3, $4, $5) RETURNING *""",
            portfolio.name,
            portfolio.description,
            user_id,
            datetime.now(timezone.utc).replace(tzinfo=None),
            datetime.now(timezone.utc).replace(tzinfo=None)
        )
        
        record_portfolio_operation("create_portfolio", "success")
        # Convert UUID to string for response
        response_dict = dict(result)
        response_dict['id'] = str(response_dict['id'])
        return response_dict
        
    except Exception as e:
        logger.error(f"Error creating portfolio: {e}")
        record_portfolio_operation("create_portfolio", "error")
        raise HTTPException(status_code=500, detail="Failed to create portfolio")

@router.get(
    "/brokers",
    summary="Get brokers",
    response_description="List of available brokers",
)
async def get_brokers(db=Depends(get_db_conn)):
    """Get list of available brokers."""
    try:
        # Return a list of default brokers
        brokers = [
        ]
        
        record_portfolio_operation("list_brokers", "success")
        return brokers
        
    except Exception as e:
        logger.error(f"Error getting brokers: {e}")
        record_portfolio_operation("list_brokers", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve brokers")

@router.get(
    "/{portfolio_id}",
    response_model=PortfolioWithHoldings,
    summary="Get portfolio with holdings",
    response_description="Portfolio details including all current holdings with instrument metadata.",
    responses={404: {"description": "Portfolio not found"}},
)
async def get_portfolio(portfolio_id: uuid.UUID, current_user: dict = Depends(get_current_user), db=Depends(get_db_conn)):
    """Return a single portfolio and its full list of holdings for the authenticated user."""
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
            """SELECT h.*, i.symbol, i.name as instrument_name, i.type as instrument_type, i.exchange, i.currency
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

@router.get(
    "/{portfolio_id}/performance",
    response_model=PerformanceSummary,
    summary="Get performance summary",
    response_description="Aggregated performance metrics: total market value, unrealized P&L, and total return %.",
    responses={404: {"description": "Portfolio not found"}},
)
async def get_portfolio_performance(portfolio_id: int, current_user: dict = Depends(get_current_user), db=Depends(get_db_conn)):
    """Return a performance summary for the given portfolio: total holdings count, market value, unrealized P&L, and total return."""
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

@router.delete(
    "/{portfolio_id}",
    summary="Delete portfolio",
    response_description="Portfolio deleted successfully.",
    responses={404: {"description": "Portfolio not found"}},
)
async def delete_portfolio(portfolio_id: str, current_user: dict = Depends(get_current_user), db=Depends(get_db_conn)):
    """Delete a portfolio by ID."""
    try:
        user_id = current_user["id"]
        
        portfolio = await db.fetchrow(
                "SELECT id FROM portfolio_service.portfolios WHERE id = $1 AND user_id = $2", 
                portfolio_id, user_id
            )
            
        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        # Delete portfolio (cascade delete will handle holdings)
        await db.execute(
            "DELETE FROM portfolio_service.portfolios WHERE id = $1 AND user_id = $2",
            portfolio_id, user_id
        )
        
        record_portfolio_operation("delete_portfolio", "success")
        return {"message": "Portfolio deleted successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting portfolio: {e}")
        record_portfolio_operation("delete_portfolio", "error")
        raise HTTPException(status_code=500, detail="Failed to delete portfolio")


@router.get(
    "/{portfolio_id}/signals",
    summary="Get portfolio Signals",
    response_description="Portfolio signals for the authenticated user.",
    responses={404: {"description": "Portfolio Signal not found"}},
)
async def get_portfolio_signals(portfolio_id: uuid.UUID, current_user: dict = Depends(get_current_user), db=Depends(get_db_conn)):
    """Return a single portfolio and its full list of holdings for the authenticated user."""
    try:
        # user_id = current_user["id"]
        
        # # Get portfolio details
        # portfolio_result = await db.fetchrow(
        #     'SELECT * FROM portfolio_service.portfolios WHERE id = $1 AND user_id = $2',
        #     portfolio_id, user_id
        # )
        
        # if not portfolio_result:
        #     raise HTTPException(status_code=404, detail="Portfolio not found")
        
        # # Get holdings with instrument details
        # holdings_result = await db.fetch(
        #     """SELECT i.id, i.symbol, i.name as instrument_name, i.type as instrument_type, i.exchange, i.currency
        #        FROM portfolio_service.holdings h
        #        JOIN portfolio_service.instruments i ON h.instrument_id = i.id
        #        WHERE h.portfolio_id = $1""",
        #     portfolio_id
        # )
        
        # portfolio_data = dict(portfolio_result)
        # portfolio_data["holdings"] = [dict(row) for row in holdings_result]
        portfolio_data = [{"symbol": "AAPL", "id": "123", "action": "buy", "confidence": 0.1, "time": datetime.now(timezone.utc).replace(tzinfo=None)}]
        
        record_portfolio_operation("get_portfolio_signals", "success")
        return portfolio_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio signals: {e}")
        record_portfolio_operation("get_portfolio_signals", "error")
        raise HTTPException(status_code=500, detail="Failed to get portfolio signals")



@router.get(
    "/{portfolio_id}/transactions",
    summary="Get portfolio transactions",
    response_description="Portfolio transactions for the authenticated user.",
    responses={404: {"description": "Portfolio transactions not found"}},
)
async def get_portfolio_transactions(portfolio_id: uuid.UUID, current_user: dict = Depends(get_current_user), db=Depends(get_db_conn)):
    """Return a single portfolio and its full list of holdings for the authenticated user."""
    try:
        # user_id = current_user["id"]
        
        # # Get portfolio details
        # portfolio_result = await db.fetchrow(
        #     'SELECT * FROM portfolio_service.portfolios WHERE id = $1 AND user_id = $2',
        #     portfolio_id, user_id
        # )
        
        # if not portfolio_result:
        #     raise HTTPException(status_code=404, detail="Portfolio not found")
        
        # # Get holdings with instrument details
        # holdings_result = await db.fetch(
        #     """SELECT i.id, i.symbol, i.name as instrument_name, i.type as instrument_type, i.exchange, i.currency
        #        FROM portfolio_service.holdings h
        #        JOIN portfolio_service.instruments i ON h.instrument_id = i.id
        #        WHERE h.portfolio_id = $1""",
        #     portfolio_id
        # )
        
        # portfolio_data = dict(portfolio_result)
        # portfolio_data["holdings"] = [dict(row) for row in holdings_result]
        portfolio_data = [{
  "id": "1234",
  "type": "buy",
  "symbol": "TSA",
  "quantity": 10,
  "price": 1,
  "transaction_date":  datetime.now(timezone.utc).replace(tzinfo=None), 
  "total_amount": 1230
}]
        
        record_portfolio_operation("get_portfolio_signals", "success")
        return portfolio_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio signals: {e}")
        record_portfolio_operation("get_portfolio_signals", "error")
        raise HTTPException(status_code=500, detail="Failed to get portfolio signals")