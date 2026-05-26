from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.concurrency import run_in_threadpool
from jose import JWTError, jwt
from app.database import get_db_conn
import yfinance as yf
from fastapi import Request
from datetime import datetime
import logging

security = HTTPBearer()
logger = logging.getLogger(__name__)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db=Depends(get_db_conn),
):
    """Validate JWT token and extract user info"""
    try:
        from app.config import settings

        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    # Fetch user from database
    user = await db.fetchrow(
        "SELECT id, username, email FROM portfolio_service.users WHERE email = $1",
        email,
    )
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(user)


async def get_user_from_request(request: Request) -> str:
    """Extract user ID from request headers (for backward compatibility)"""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
    return user_id


async def get_tikers(tickers: list[str], db):

    results = []

    for symbol in tickers:
        cached = {}
        result = (
            await db.fetch(
                "SELECT * FROM portfolio_service.instruments WHERE symbol = $1", symbol
            )
        )[0]

        should_refresh = True

        if result and result.get("updated_at"):
            should_refresh = result.get("updated_at").date() < datetime.utcnow().date()

        # FULL REFRESH ONCE A DAY
        if should_refresh:
            ticker = await run_in_threadpool(lambda: yf.Ticker(symbol))
            fast_info = await run_in_threadpool(ticker.get_fast_info)

            cached["previous_close"] = fast_info.get("previousClose")
            cached["current_price"] = fast_info.get("lastPrice")

            result = await db.fetchrow(
                """update portfolio_service.instruments
               set previous_close=$1 where symbol = $2 returning *""",
                cached["previous_close"],
                symbol,
            )

        # ONLY LIVE PRICE UPDATE
        else:
            ticker = await run_in_threadpool(lambda: yf.Ticker(symbol))

            fast_info = await run_in_threadpool(ticker.get_fast_info)

            cached["current_price"] = fast_info.get("lastPrice")

        results.append(
            {
                "symbol": result["symbol"],
                "name": result["name"],
                "current_price": cached["current_price"],
                "change_percent": (
                    (cached["current_price"] - float(result["previous_close"]))
                    / float(result["previous_close"])
                )
                * 100
                if result["previous_close"]
                else 0,
            }
        )

    return results


async def update_tickers(db):
    results = []
    try:
        # 1. Fetch from DB
        rows = await db.fetch("SELECT symbol FROM portfolio_service.instruments")
        if not rows:
            raise HTTPException(status_code=404, detail="Instruments not found")

        result_symbols = [row["symbol"] for row in rows]

        # 2. Initialize Tickers in threadpool
        # Passing a list directly to yf.Tickers works better than a space-separated string in newer versions
        tickers_dict = await run_in_threadpool(
            lambda: yf.Tickers(result_symbols).tickers
        )

        # 3. Loop through and update
        for symbol in result_symbols:
            try:
                # Safely get the ticker object from the dictionary
                ticker_obj = tickers_dict.get(symbol)
                if not ticker_obj:
                    logger.warning(f"Ticker object not found for {symbol}")
                    continue

                # Fetch fast_info inside the threadpool safely
                fast_info = await run_in_threadpool(lambda: ticker_obj.fast_info)

                # yfinance uses snake_case for fast_info attributes
                prev_close = fast_info.previous_close

                if prev_close is None:
                    logger.warning(f"No previous close data available for {symbol}")
                    continue

                # 4. Update the DB asynchronously
                await db.execute(
                    """
                    UPDATE portfolio_service.instruments
                    SET previous_close = $1 
                    WHERE symbol = $2
                    """,
                    prev_close,
                    symbol,
                )
                results.append(symbol)

            except Exception as item_error:
                # Keeps the loop moving if one ticker fails
                logger.error(f"Failed to update single ticker {symbol}: {item_error}")
                continue

        return results

    except Exception as e:
        logger.error(f"Global error updating tickers: {e}")
        return results
