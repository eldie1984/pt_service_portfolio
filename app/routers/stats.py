from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
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
    "/{portfolio_id}/transaction_log",
    summary="Get portfolio transaction log",
    response_description="Portfolio transaction log for the authenticated user.",
    responses={404: {"description": "Portfolio transaction log not found"}},
)
async def get_portfolio_transaction_log(
    portfolio_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db_conn),
):
    """Return a single portfolio and its full list of holdings for the authenticated user."""
    try:
        user_id = current_user["id"]

        # Get portfolio details
        portfolio_result = await db.fetchrow(
            "SELECT * FROM portfolio_service.portfolios WHERE id = $1 AND user_id = $2",
            portfolio_id,
            user_id,
        )

        if not portfolio_result:
            raise HTTPException(status_code=404, detail="Portfolio not found")

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
        #         portfolio_data = [{
        #   "id": "1234",
        #   "type": "buy",
        #   "symbol": "TSA",
        #   "quantity": 10,
        #   "price": 1,
        #   "transaction_date":  datetime.now(timezone.utc).replace(tzinfo=None),
        #   "total_amount": 1230
        # }]
        potfolio_transactions = await db.fetch(
            """select t.id,tr.type, i.symbol, t.quantity, ROUND(t.amount,3) as price, t.date_added as transaction_date from transaction_service.transaction_detail t
LEFT JOIN portfolio_service.instruments i ON t.instrument_id = i.id
left join transaction_service.transactions tr on t.transaction_id = tr.id
where date(t.date_added) = CURRENT_DATE"""
        )
        portfolio_data = [dict(row) for row in potfolio_transactions]
        record_portfolio_operation("get_portfolio_signals", "success")
        return portfolio_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting portfolio signals: {e}")
        record_portfolio_operation("get_portfolio_signals", "error")
        raise HTTPException(status_code=500, detail="Failed to get portfolio signals")


@router.get(
    "/",
    summary="Get stats",
    response_description="List of available brokers",
)
async def get_stats(db=Depends(get_db_conn)):
    """Get list of available brokers."""
    try:
        # Return a list of default brokers
        cash_balance_row = await db.fetchrow(
            "select currency,amount from portfolio_service.cash"
        )

        # Get total value by currency (list of rows)
        total_value_rows = await db.fetch("""select sum(h.market_value) as amount
        ,sum(h.quantity*(h.market_value - i.previous_close)) as day_change
        , i.currency, count(*) as positions
        from portfolio_service.holdings h
        left join portfolio_service.instruments i on h.instrument_id = i.id
         group by i.currency""")

        # Get currency mapping
        tx_rows = await db.fetch(
            """SELECT value,date FROM "portfolio_service"."currency_mapping" where from_currency = 'USD' and to_currency = 'ARS' order by date limit 1"""
        )

        portfolio_data = {}

        # Handle cash balance (single row or None)
        if cash_balance_row:
            portfolio_data["cash"] = {
                cash_balance_row["currency"]: cash_balance_row["amount"]
            }
        else:
            portfolio_data["cash"] = {}

        # Handle total value (list of rows)
        portfolio_data["market_value"] = {
            row["currency"]: row["amount"] for row in total_value_rows
        }
        portfolio_data["total_pnl"] = {
            row["currency"]: row["day_change"] for row in total_value_rows
        }
        portfolio_data["day_change_percent"] = 0.69

        # Handle FX rates (list with optional first element)
        if tx_rows:
            portfolio_data["fx"] = {
                "usd_to_ars": tx_rows[0]["value"],
                "usd_to_ars_date": tx_rows[0]["date"],
            }
        else:
            portfolio_data["fx"] = {"usd_to_ars": None, "usd_to_ars_date": None}

        record_portfolio_operation("stats_portfolio", "success")
        # return portfolio_data
        return {
            "cash": {"usd": 12500.00, "ars": 13131250.00},
            "total_pnl": {"usd": 1840.50, "ars": 1933445.25},
            "total_pnl_percent": 3.42,
            "positions": 6,
            "orders": 23,
            "win_rate": 0.62,
            "signals": 4,
            "market_value": {"usd": 47230.18, "ars": 49605294.09},
            "fx": {"usd_ars": 1050.5, "as_of": "2026-05-17T13:00:00Z"},
        }

    except Exception as e:
        logger.error(f"Error getting brokers: {e}")
        record_portfolio_operation("list_brokers", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve brokers")
