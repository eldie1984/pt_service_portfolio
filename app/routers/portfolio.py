from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
import logging
import uuid


from app.database import get_db_conn
from app.metrics import record_portfolio_operation
from .utils import get_current_user

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
async def get_portfolios(
    current_user: dict = Depends(get_current_user), db=Depends(get_db_conn)
):
    """Return all portfolios that belong to the authenticated user."""
    try:
        user_id = str(current_user["id"])

        result = await db.fetch(
            "SELECT cast(id as text) as id, cast(user_id as text) as user_id, name, description , created_at, updated_at,currency FROM portfolio_service.portfolios WHERE user_id = $1 ORDER BY created_at DESC",
            user_id,
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
    db=Depends(get_db_conn),
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
            datetime.now(timezone.utc).replace(tzinfo=None),
        )

        record_portfolio_operation("create_portfolio", "success")
        # Convert UUID to string for response
        response_dict = dict(result)
        response_dict["id"] = str(response_dict["id"])
        return response_dict

    except Exception as e:
        logger.error(f"Error creating portfolio: {e}")
        record_portfolio_operation("create_portfolio", "error")
        raise HTTPException(status_code=500, detail="Failed to create portfolio")


@router.get(
    "/{portfolio_id}",
    # response_model=PortfolioWithHoldings,
    summary="Get portfolio with holdings",
    response_description="Portfolio details including all current holdings with instrument metadata.",
    responses={404: {"description": "Portfolio not found"}},
)
async def get_portfolio(
    portfolio_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db_conn),
):
    """Return a single portfolio and its full list of holdings for the authenticated user."""
    try:
        user_id = current_user["id"]

        # Get portfolio details
        portfolio_result = await db.fetchrow(
            "SELECT id,name,portfolios.currency FROM portfolio_service.portfolios WHERE id = $1 AND user_id = $2",
            portfolio_id,
            user_id,
        )

        if not portfolio_result:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        # Get cash balance (single row or None)
        cash_balance_row = await db.fetchrow(
            "select currency,amount from portfolio_service.cash where portfolio_id = $1",
            portfolio_id,
        )

        # Get total value by currency (list of rows)
        total_value_rows = await db.fetch(
            """select sum(h.market_value) as amount
        ,sum(h.quantity*(h.market_value - i.previous_close)) as day_change
        , i.currency
        from portfolio_service.holdings h
        left join portfolio_service.instruments i on h.instrument_id = i.id
         where h.portfolio_id = $1 group by i.currency""",
            portfolio_id,
        )

        # Get holdings with instrument details
        holdings_result = await db.fetch(
            """SELECT h.id
                , i.symbol
                , i.currency
                ,h.quantity
                ,h.average_cost
                ,i.previous_close as market_value
                ,h.quantity*(i.previous_close-h.average_cost) as unrealized_pnl
                , i.type as instrument_type, i.exchange
               FROM portfolio_service.holdings h
               JOIN portfolio_service.instruments i ON h.instrument_id = i.id
               WHERE h.portfolio_id = $1""",
            portfolio_id,
        )

        # Get currency mapping
        tx_rows = await db.fetch(
            """SELECT value,date FROM "portfolio_service"."currency_mapping" where from_currency = 'USD' and to_currency = 'ARS' order by date limit 1"""
        )

        portfolio_data = dict(portfolio_result)

        # Handle cash balance (single row or None)
        if cash_balance_row:
            portfolio_data["cash_balance"] = {
                cash_balance_row["currency"]: cash_balance_row["amount"]
            }
        else:
            portfolio_data["cash_balance"] = {}

        # Handle total value (list of rows)
        portfolio_data["total_value"] = {
            row["currency"]: row["amount"] for row in total_value_rows
        }
        portfolio_data["day_change"] = {
            row["currency"]: row["day_change"] for row in total_value_rows
        }
        portfolio_data["day_change_percent"] = 0.69
        portfolio_data["holdings"] = [dict(row) for row in holdings_result]

        # Handle FX rates (list with optional first element)
        if tx_rows:
            portfolio_data["fx"] = {
                "usd_to_ars": tx_rows[0]["value"],
                "usd_to_ars_date": tx_rows[0]["date"],
            }
        else:
            portfolio_data["fx"] = {"usd_to_ars": None, "usd_to_ars_date": None}

        record_portfolio_operation("get_portfolio", "success")
        #         return {
        #   "id": 7,
        #   "name": "Main",
        #   "currency": "USD",
        #   "cash_balance":        { "usd": 12500.00, "ars": 13131250.00 },
        #   "total_value":         { "usd": 59730.18, "ars": 62736544.09 },
        #   "day_change":          { "usd": 412.07,   "ars": 432879.54 },
        #   "day_change_percent": 0.69,

        #   "holdings": [
        #     {
        #       "id": 101,
        #       "symbol": "AAPL",
        #       "currency": "USD",
        #       "quantity": 50,
        #       "average_cost": 175.20,
        #       "market_value": 9372.50,
        #       "unrealized_pnl": 612.50
        #     },
        #     {
        #       "id": 102,
        #       "symbol": "MSFT",
        #       "currency": "USD",
        #       "quantity": 20,
        #       "average_cost": 415.00,
        #       "market_value": 8492.00,
        #       "unrealized_pnl": 192.00
        #     },
        #     {
        #       "id": 103,
        #       "symbol": "YPF.BA",
        #       "currency": "ARS",
        #       "quantity": 1500,
        #       "average_cost": 18500.00,
        #       "market_value": 31425000.00,
        #       "unrealized_pnl": 3675000.00
        #     }
        #   ],

        #   "fx": { "usd_ars": 1050.5, "as_of": "2026-05-17T13:00:00Z" }
        # }
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
async def get_portfolio_performance(
    portfolio_id: int,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db_conn),
):
    """Return a performance summary for the given portfolio: total holdings count, market value, unrealized P&L, and total return."""
    try:
        user_id = current_user["id"]

        # Verify portfolio ownership
        portfolio_result = await db.fetchrow(
            "SELECT * FROM portfolio_service.portfolios WHERE id = $1 AND user_id = $2",
            portfolio_id,
            user_id,
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
            portfolio_id,
        )

        performance = dict(performance_result)
        total_market_value = float(performance["total_market_value"])
        total_unrealized_pnl = float(performance["total_unrealized_pnl"])

        performance_summary = PerformanceSummary(
            portfolioId=portfolio_id,
            totalHoldings=int(performance["total_holdings"]),
            totalMarketValue=total_market_value,
            totalUnrealizedPnL=total_unrealized_pnl,
            totalReturn=(total_unrealized_pnl / total_market_value * 100)
            if total_market_value > 0
            else 0,
        )

        record_portfolio_operation("get_performance", "success")
        return performance_summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio performance: {e}")
        record_portfolio_operation("get_performance", "error")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve performance metrics"
        )


@router.delete(
    "/{portfolio_id}",
    summary="Delete portfolio",
    response_description="Portfolio deleted successfully.",
    responses={404: {"description": "Portfolio not found"}},
)
async def delete_portfolio(
    portfolio_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db_conn),
):
    """Delete a portfolio by ID."""
    try:
        user_id = current_user["id"]

        portfolio = await db.fetchrow(
            "SELECT id FROM portfolio_service.portfolios WHERE id = $1 AND user_id = $2",
            portfolio_id,
            user_id,
        )

        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        # Delete portfolio (cascade delete will handle holdings)
        await db.execute(
            "DELETE FROM portfolio_service.portfolios WHERE id = $1 AND user_id = $2",
            portfolio_id,
            user_id,
        )

        record_portfolio_operation("delete_portfolio", "success")
        return {"message": "Portfolio deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting portfolio: {e}")
        record_portfolio_operation("delete_portfolio", "error")
        raise HTTPException(status_code=500, detail="Failed to delete portfolio")
