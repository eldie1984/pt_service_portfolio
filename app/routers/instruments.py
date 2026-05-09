from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Annotated
import logging
from jose import JWTError, jwt

from app.database.connection import get_db
from app.metrics import record_portfolio_operation

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
    id: int
    symbol: str
    name: str
    type: str
    exchange: str
    currency: str
    created_at: datetime
    updated_at: datetime

@router.get("/")
async def get_instruments(current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Get all available instruments"""
    try:
        result = await db.fetch(
            'SELECT * FROM portfolio_service.instruments ORDER BY symbol'
        )
        
        record_portfolio_operation("list_instruments", "success")
        return [dict(row) for row in result]
        
    except Exception as e:
        logger.error(f"Error getting instruments: {e}")
        record_portfolio_operation("list_instruments", "error")
        raise HTTPException(status_code=500, detail="Failed to retrieve instruments")

@router.post("/", status_code=201)
async def create_instrument(
    instrument: InstrumentCreate, 
    current_user: dict = Depends(get_current_user),
    db=Depends(get_db)
):
    """Create new instrument"""
    try:
        result = await db.fetchrow(
            """INSERT INTO portfolio_service.instruments (symbol, name, type, exchange, currency) 
               VALUES ($1, $2, $3, $4, $5) RETURNING *""",
            instrument.symbol, instrument.name, instrument.type, instrument.exchange, instrument.currency
        )
        
        record_portfolio_operation("create_instrument", "success")
        return dict(result)
        
    except Exception as e:
        logger.error(f"Error creating instrument: {e}")
        record_portfolio_operation("create_instrument", "error")
        raise HTTPException(status_code=500, detail="Failed to create instrument")

@router.get("/{instrument_id}")
async def get_instrument(instrument_id: int, current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Get specific instrument"""
    try:
        result = await db.fetchrow(
            'SELECT * FROM portfolio_service.instruments WHERE id = $1',
            instrument_id
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

@router.get("/symbol/{symbol}")
async def get_instrument_by_symbol(symbol: str, current_user: dict = Depends(get_current_user), db=Depends(get_db)):
    """Get instrument by symbol"""
    try:
        result = await db.fetchrow(
            'SELECT * FROM portfolio_service.instruments WHERE symbol = $1',
            symbol.upper()
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
