import asyncpg
from asyncpg import Pool
import asyncio
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Database:
    pool: Optional[Pool] = None
    _database_url: Optional[str] = None

    @classmethod
    async def connect(cls, database_url: str):
        cls._database_url = database_url
        if cls.pool:
            return  # Ya está conectado

        try:
            cls.pool = await asyncpg.create_pool(
                database_url,
                min_size=5,
                max_size=20,
                command_timeout=60,
                # Ayuda a detectar conexiones muertas antes de usarlas
                max_inactive_connection_lifetime=300,
            )
            logger.info("Database connection pool created")
        except Exception as e:
            logger.error(f"Failed to create pool: {e}")
            raise

    @classmethod
    async def disconnect(cls):
        if cls.pool:
            # Usamos wait=True para asegurar que las peticiones en curso terminen
            # antes de que el objeto se destruya por completo
            await asyncio.wait_for(cls.pool.close(), timeout=10.0)
            cls.pool = None
            logger.info("Database connection pool closed safely")


async def init_db():
    """Initialize database connection"""
    from app.config import settings

    await Database.connect(settings.DATABASE_URL)


async def get_db():
    """Dependency to get database connection"""
    pool = await Database.get_connection()
    return pool


async def get_db_conn():
    """
    Context manager para ser usado en los routers.
    Garantiza que la conexión se devuelva al pool pase lo que pase.
    """
    if not Database.pool or Database.pool._closed:
        raise RuntimeError("Database pool is not initialized or closing")

    async with Database.pool.acquire() as connection:
        yield connection
