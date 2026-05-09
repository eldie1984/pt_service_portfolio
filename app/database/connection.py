import asyncpg
from asyncpg import Pool
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class Database:
    pool: Optional[Pool] = None

    @classmethod
    async def connect(cls, database_url: str) -> Pool:
        """Create database connection pool"""
        try:
            cls.pool = await asyncpg.create_pool(
                database_url,
                min_size=5,
                max_size=20,
                command_timeout=60
            )
            logger.info("Database connection pool created successfully")
            return cls.pool
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise

    @classmethod
    async def disconnect(cls):
        """Close database connection pool"""
        if cls.pool:
            await cls.pool.close()
            cls.pool = None
            logger.info("Database connection pool closed")

    @classmethod
    async def get_connection(cls):
        """Get a database connection from the pool"""
        if not cls.pool:
            raise RuntimeError("Database pool not initialized")
        return cls.pool

async def init_db():
    """Initialize database connection"""
    from app.config import settings
    await Database.connect(settings.DATABASE_URL)

async def get_db():
    """Dependency to get database connection"""
    return await Database.get_connection()
