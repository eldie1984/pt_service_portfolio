from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from app.database import get_db_conn

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), 
    db = Depends(get_db_conn)):
    """Validate JWT token and extract user info"""
    try:
        from app.config import settings
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    # Fetch user from database
    user = await db.fetchrow(
            "SELECT id, username, email FROM portfolio_service.users WHERE email = $1",
            email
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