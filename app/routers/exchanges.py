from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID
import logging
import asyncio

from app.database import get_db_conn
from app.metrics import record_portfolio_operation

router = APIRouter()
logger = logging.getLogger(__name__)


class ExchangeCreate(BaseModel):
    name: str
    type: str  # 'stock' | 'crypto' | 'bond' | 'commodity' | 'forex'
    country: Optional[str] = None
    code: Optional[str] = None
    is_active: bool = True


class ExchangeResponse(BaseModel):
    id: str
    name: str
    type: str
    country: Optional[str]
    code: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {UUID: str}


@router.get(
    "",
    response_model=List[ExchangeResponse],
    summary="List exchanges",
    response_description="All active exchanges ordered by name, optionally filtered by type.",
)
@router.get(
    "/",
    response_model=List[ExchangeResponse],
    summary="List exchanges",
    response_description="All active exchanges ordered by name, optionally filtered by type.",
    include_in_schema=False,
)
async def get_exchanges(
    type: Optional[str] = Query(
        None,
        description="Filter exchanges by type (stock, crypto, bond, commodity, forex)",
    ),
    db=Depends(get_db_conn),
):
    """Return all active trading venues ordered by name, optionally filtered by type."""
    try:
        if type:
            query = "SELECT * FROM portfolio_service.exchanges WHERE is_active = true AND type = $1 ORDER BY name"
            result = await db.fetch(query, type)
        else:
            query = "SELECT * FROM portfolio_service.exchanges WHERE is_active = true ORDER BY name"
            result = await db.fetch(query)

        record_portfolio_operation("list_exchanges", "success")
        # Convert UUID to string for response
        exchanges_list = []
        for row in result:
            row_dict = dict(row)
            row_dict["id"] = str(row_dict["id"])
            exchanges_list.append(row_dict)
        return exchanges_list
    except Exception as e:
        logger.error(f"Error getting exchanges: {e}")
        record_portfolio_operation("list_exchanges", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve exchanges")


@router.post(
    "/",
    response_model=ExchangeResponse,
    status_code=201,
    summary="Create exchange",
    response_description="The newly created exchange.",
)
async def create_exchange(exchange: ExchangeCreate, db=Depends(get_db_conn)):
    """Create a new trading venue. `type` must be one of: `stock`, `crypto`, `bond`, `commodity`, `forex`."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = await db.fetchrow(
                """INSERT INTO portfolio_service.exchanges (name, type, country, code, is_active, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *""",
                exchange.name,
                exchange.type,
                exchange.country,
                exchange.code,
                exchange.is_active,
                datetime.utcnow(),
                datetime.utcnow(),
            )
            record_portfolio_operation("create_exchange", "success")
            # Convert UUID to string for response
            response_dict = dict(result)
            response_dict["id"] = str(response_dict["id"])
            return response_dict
        except Exception as e:
            if "duplicate key" in str(e):
                logger.error(f"Duplicate exchange code: {e}")
                record_portfolio_operation("create_exchange", "error")
                raise HTTPException(
                    status_code=409, detail="Exchange with this code already exists"
                )
            elif "pool is closed" in str(e) and attempt < max_retries - 1:
                logger.warning(
                    f"Database pool closed, retrying (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
                continue
            else:
                logger.error(f"Error creating exchange: {e}")
                record_portfolio_operation("create_exchange", "error")
                raise HTTPException(status_code=500, detail="Failed to create exchange")


@router.delete(
    "/{exchange_id}",
    summary="Delete exchange",
    response_description="Exchange deleted successfully.",
    responses={404: {"description": "Exchange not found"}},
)
async def delete_exchange(exchange_id: str, db=Depends(get_db_conn)):
    """Delete an exchange by ID."""
    try:
        # First check if exchange exists
        exchange = await db.fetchrow(
            "SELECT id FROM portfolio_service.exchanges WHERE id = $1", exchange_id
        )

        if not exchange:
            raise HTTPException(status_code=404, detail="Exchange not found")

        # Delete exchange
        await db.execute(
            "DELETE FROM portfolio_service.exchanges WHERE id = $1", exchange_id
        )

        record_portfolio_operation("delete_exchange", "success")
        return {"message": "Exchange deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting exchange: {e}")
        record_portfolio_operation("delete_exchange", "error")
        raise HTTPException(status_code=500, detail="Failed to delete exchange")


@router.get(
    "/{type_id}",
    summary="Get exchange by ID",
    response_description="Exchanges by type.",
    responses={404: {"description": "Exchange type not found"}},
)
async def get_exchanges_by_type(exchange_type: str, db=Depends(get_db_conn)):
    """Return List of exchanges by type."""
    try:
        result = await db.fetchrow(
            "SELECT * FROM portfolio_service.exchanges WHERE is_active = true and type = $1 ORDER BY name ",
            exchange_type,
        )

        record_portfolio_operation("list_exchanges", "success")
        # Convert UUID to string for response
        exchanges_list = []
        for row in result:
            row_dict = dict(row)
            row_dict["id"] = str(row_dict["id"])

            exchanges_list.append(row_dict)
        return exchanges_list
    except Exception as e:
        logger.error(f"Error getting exchanges: {e}")
        record_portfolio_operation("list_exchanges", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve exchanges")
