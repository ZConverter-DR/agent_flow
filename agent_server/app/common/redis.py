import redis.asyncio
from app.common.config import settings

redis_client = redis.asyncio.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True
)

async def get_redis() -> redis.asyncio.Redis:
    return redis_client