import redis.asyncio as aioredis
from app.config import get_settings

settings = get_settings()

# Single async Redis client reused across requests
_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        if settings.redis_url:
            # Railway / any remote Redis — use the full connection URL
            _redis_client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        else:
            # Local Redis (host + port + password)
            _redis_client = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password or None,
                db=settings.redis_db,
                decode_responses=True,
            )
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None