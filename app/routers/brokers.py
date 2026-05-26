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


class BrokerCreate(BaseModel):
    name: str
    type: Optional[str] = None  # 'stock' | 'crypto' | 'bond' | 'commodity' | 'forex'
    commision: Optional[float] = None
    is_active: bool = True


class BrokerResponse(BaseModel):
    id: str
    name: str
    type: Optional[str] = None
    commision: Optional[float] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {UUID: str}


@router.get(
    "",
    response_model=List[BrokerResponse],
    summary="List exchanges",
    response_description="All active exchanges ordered by name, optionally filtered by type.",
)
@router.get(
    "/",
    response_model=List[BrokerResponse],
    summary="List exchanges",
    response_description="All active exchanges ordered by name, optionally filtered by type.",
    include_in_schema=False,
)
async def get_brokers(
    type: Optional[str] = Query(
        None,
        description="Filter exchanges by type (stock, crypto, bond, commodity, forex)",
    ),
    db=Depends(get_db_conn),
):
    """Return all active trading venues ordered by name, optionally filtered by type."""
    try:
        if type:
            query = "SELECT * FROM portfolio_service.brokers WHERE is_active = true AND type = $1 ORDER BY name"
            result = await db.fetch(query, type)
        else:
            query = "SELECT * FROM portfolio_service.brokers WHERE is_active = true ORDER BY name"
            result = await db.fetch(query)

        record_portfolio_operation("list_brokers", "success")
        # Convert UUID to string for response
        brokers_list = []
        for row in result:
            row_dict = dict(row)
            row_dict["id"] = str(row_dict["id"])
            brokers_list.append(row_dict)
        return brokers_list
    except Exception as e:
        logger.error(f"Error getting brokers: {e}")
        record_portfolio_operation("list_brokers", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve brokers")


@router.post(
    "/",
    response_model=BrokerResponse,
    status_code=201,
    summary="Create broker",
    response_description="The newly created broker.",
)
async def create_broker(broker: BrokerCreate, db=Depends(get_db_conn)):
    """Create a new trading venue. `type` must be one of: `stock`, `crypto`, `bond`, `commodity`, `forex`."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = await db.fetchrow(
                """INSERT INTO portfolio_service.brokers (name, type, commision, is_active, created_at, updated_at)
                       VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
                broker.name,
                broker.type,
                broker.commision,
                broker.is_active,
                datetime.utcnow(),
                datetime.utcnow(),
            )
            record_portfolio_operation("create_broker", "success")
            # Convert UUID to string for response
            response_dict = dict(result)
            response_dict["id"] = str(response_dict["id"])
            return response_dict
        except Exception as e:
            if "duplicate key" in str(e):
                logger.error(f"Duplicate broker name: {e}")
                record_portfolio_operation("create_broker", "error")
                raise HTTPException(
                    status_code=409, detail="Broker with this name already exists"
                )
            elif "pool is closed" in str(e) and attempt < max_retries - 1:
                logger.warning(
                    f"Database pool closed, retrying (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
                continue
            else:
                logger.error(f"Error creating broker: {e}")
                record_portfolio_operation("create_broker", "error")
                raise HTTPException(status_code=500, detail="Failed to create broker")


@router.delete(
    "/{broker_id}",
    summary="Delete broker",
    response_description="Broker deleted successfully.",
    responses={404: {"description": "Broker not found"}},
)
async def delete_broker(broker_id: str, db=Depends(get_db_conn)):
    """Delete a broker by ID."""
    try:
        # First check if broker exists
        broker = await db.fetchrow(
            "SELECT id FROM portfolio_service.brokers WHERE id = $1", broker_id
        )

        if not broker:
            raise HTTPException(status_code=404, detail="Broker not found")

        # Delete broker
        await db.execute(
            "DELETE FROM portfolio_service.brokers WHERE id = $1", broker_id
        )

        record_portfolio_operation("delete_broker", "success")
        return {"message": "Broker deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting broker: {e}")
        record_portfolio_operation("delete_broker", "error")
        raise HTTPException(status_code=500, detail="Failed to delete broker")


@router.get(
    "/{type_id}",
    summary="Get broker by ID",
    response_description="Brokers by type.",
    responses={404: {"description": "Broker type not found"}},
)
async def get_brokers_by_type(broker_type: str, db=Depends(get_db_conn)):
    """Return List of brokers by type."""
    try:
        result = await db.fetchrow(
            "SELECT * FROM portfolio_service.brokers WHERE is_active = true and type = $1 ORDER BY name ",
            broker_type,
        )

        record_portfolio_operation("list_brokers", "success")
        # Convert UUID to string for response
        brokers_list = []
        for row in result:
            row_dict = dict(row)
            row_dict["id"] = str(row_dict["id"])

            brokers_list.append(row_dict)
        return brokers_list
    except Exception as e:
        logger.error(f"Error getting brokers: {e}")
        record_portfolio_operation("list_brokers", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve brokers")
