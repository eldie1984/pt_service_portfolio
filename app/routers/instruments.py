from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel
import uuid
import logging

from datetime import datetime

from app.database import get_db_conn
from app.metrics import record_portfolio_operation
from .utils import get_current_user, get_tikers, update_tickers


security = HTTPBearer()
router = APIRouter()
logger = logging.getLogger(__name__)


# Pydantic models
class InstrumentCreate(BaseModel):
    symbol: str
    name: str
    type: str
    exchange: str
    currency: str


class InstrumentResponse(BaseModel):
    id: uuid.UUID
    symbol: str
    name: str
    type: str
    exchange: str
    currency: str
    created_at: datetime
    updated_at: datetime


@router.get(
    "/update_instruments",
    summary="Update instruments",
    response_description="Update instruments. This endpoint is used to update the instruments table.",
    responses={404: {"description": "Instrument not found"}},
)
async def update_instruments(db=Depends(get_db_conn)):
    """Return a single instrument by its ticker symbol (e.g. `AAPL`, `BTC`). Case-insensitive."""
    try:
        updated_symbols = await update_tickers(db)

        record_portfolio_operation("update_instruments", "success")
        return {"status": "success", "updated_tickers": updated_symbols}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting instrument by symbol: {e}")
        record_portfolio_operation("get_instrument", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve instrument")


@router.get(
    "/watchlist",
    summary="List instruments",
    response_description="All instruments ordered by symbol.",
)
async def get_watchlist(
    current_user: dict = Depends(get_current_user), db=Depends(get_db_conn)
):
    """Return all tradeable instruments available in the system."""
    try:
        record_portfolio_operation("watchlist", "success")
        return await get_tikers(["GGAL.BA"], db)

    except Exception as e:
        logger.error(f"Error getting instruments: {e}")
        record_portfolio_operation("list_instruments", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve instruments")


@router.get(
    "/tickerbar",
    summary="List instruments",
    response_description="All instruments ordered by symbol.",
)
async def get_tickerbar(
    current_user: dict = Depends(get_current_user), db=Depends(get_db_conn)
):
    """Return all tradeable instruments available in the system."""
    try:
        record_portfolio_operation("tickerbar", "success")
        return await get_tikers(["GGALD.BA"], db)

    except Exception as e:
        logger.error(f"Error getting instruments: {e}")
        record_portfolio_operation("list_instruments", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve instruments")


@router.get(
    "/",
    summary="List instruments",
    response_description="All instruments ordered by symbol.",
)
async def get_instruments(
    current_user: dict = Depends(get_current_user), db=Depends(get_db_conn)
):
    """Return all tradeable instruments available in the system."""
    try:
        result = await db.fetch(
            "SELECT * FROM portfolio_service.instruments ORDER BY symbol"
        )

        record_portfolio_operation("list_instruments", "success")
        return [dict(row) for row in result]

    except Exception as e:
        logger.error(f"Error getting instruments: {e}")
        record_portfolio_operation("list_instruments", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve instruments")


@router.post(
    "/",
    status_code=201,
    summary="Create instrument",
    response_description="The newly created instrument.",
)
async def create_instrument(
    instrument: InstrumentCreate,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db_conn),
):
    """Create a new tradeable instrument."""
    try:
        result = await db.fetchrow(
            """INSERT INTO portfolio_service.instruments (symbol, name, type, exchange, currency) 
               VALUES ($1, $2, $3, $4, $5) RETURNING *""",
            instrument.symbol,
            instrument.name,
            instrument.type,
            instrument.exchange,
            instrument.currency,
        )

        record_portfolio_operation("create_instrument", "success")
        return dict(result)

    except Exception as e:
        logger.error(f"Error creating instrument: {e}")
        record_portfolio_operation("create_instrument", "error")
        raise HTTPException(status_code=500, detail="Failed to create instrument")


@router.get(
    "/{instrument_id}",
    summary="Get instrument by ID",
    response_description="Instrument details.",
    responses={404: {"description": "Instrument not found"}},
)
async def get_instrument(
    instrument_id: int,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db_conn),
):
    """Return a single instrument by its numeric ID."""
    try:
        result = await db.fetchrow(
            "SELECT * FROM portfolio_service.instruments limit $1", instrument_id
        )

        if not result:
            raise HTTPException(status_code=404, detail="Instrument not found")

        record_portfolio_operation("get_instrument", "success")
        return dict(result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting instrument: {e}")
        record_portfolio_operation("get_instrument", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve instrument")


@router.delete(
    "/{instrument_id}",
    summary="Delete instrument",
    response_description="Instrument deleted successfully.",
    responses={404: {"description": "Instrument not found"}},
)
async def delete_instrument(
    instrument_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db_conn),
):
    """Delete an instrument by ID."""
    try:
        # First check if instrument exists
        instrument = await db.fetchrow(
            "SELECT id FROM portfolio_service.instruments WHERE id = $1", instrument_id
        )

        if not instrument:
            raise HTTPException(status_code=404, detail="Instrument not found")

        # Delete instrument
        await db.execute(
            "DELETE FROM portfolio_service.instruments WHERE id = $1", instrument_id
        )

        record_portfolio_operation("delete_instrument", "success")
        return {"message": "Instrument deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting instrument: {e}")
        record_portfolio_operation("delete_instrument", "error")
        raise HTTPException(status_code=500, detail="Failed to delete instrument")


@router.get(
    "/symbol/{symbol}",
    summary="Get instrument by symbol",
    response_description="Instrument details. Symbol lookup is case-insensitive.",
    responses={404: {"description": "Instrument not found"}},
)
async def get_instrument_by_symbol(
    symbol: str, current_user: dict = Depends(get_current_user), db=Depends(get_db_conn)
):
    """Return a single instrument by its ticker symbol (e.g. `AAPL`, `BTC`). Case-insensitive."""
    try:
        result = await db.fetchrow(
            "SELECT * FROM portfolio_service.instruments WHERE symbol = $1",
            symbol.upper(),
        )

        if not result:
            raise HTTPException(status_code=404, detail="Instrument not found")

        record_portfolio_operation("get_instrument", "success")
        return dict(result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting instrument by symbol: {e}")
        record_portfolio_operation("get_instrument", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve instrument")
