from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID
import logging

from app.database.connection import get_db
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
        json_encoders = {
            UUID: str
        }


@router.get("/", response_model=List[ExchangeResponse])
async def get_exchanges(db=Depends(get_db)):
    """Get all exchanges"""
    try:
        async with db.acquire() as connection:
            result = await connection.fetch(
                "SELECT * FROM portfolio_service.exchanges WHERE is_active = true ORDER BY name"
            )
            record_portfolio_operation("list_exchanges", "success")
            # Convert UUID to string for response
            exchanges_list = []
            for row in result:
                row_dict = dict(row)
                row_dict['id'] = str(row_dict['id'])
                exchanges_list.append(row_dict)
            return exchanges_list
    except Exception as e:
        logger.error(f"Error getting exchanges: {e}")
        record_portfolio_operation("list_exchanges", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve exchanges")


@router.post("/", response_model=ExchangeResponse, status_code=201)
async def create_exchange(exchange: ExchangeCreate, db=Depends(get_db)):
    """Create a new exchange"""
    try:
        async with db.acquire() as connection:
            result = await connection.fetchrow(
                """INSERT INTO portfolio_service.exchanges (name, type, country, code, is_active, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *""",
                exchange.name, exchange.type, exchange.country, exchange.code, exchange.is_active,
                datetime.utcnow(), datetime.utcnow()
            )
            record_portfolio_operation("create_exchange", "success")
            # Convert UUID to string for response
            response_dict = dict(result)
            response_dict['id'] = str(response_dict['id'])
            return response_dict
    except Exception as e:
        logger.error(f"Error creating exchange: {e}")
        record_portfolio_operation("create_exchange", "error")
        raise HTTPException(status_code=500, detail="Failed to create exchange")
