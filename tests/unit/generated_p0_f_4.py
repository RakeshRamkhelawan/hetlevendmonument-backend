"""
Task: P0.F.4 - Kill Redis -> App returns 503, no crash

Description:
- Implement graceful degradation when Redis is unavailable.
- Ensure the app returns a 503 Service Unavailable response without crashing.

Author: SanskritiSetu.org
Date: December 8, 2025
"""

from fastapi import Depends, FastAPI, HTTPException
from redis.asyncio import ConnectionError, Redis

from src.core.middleware.tenant_middleware import TenantMiddleware

app = FastAPI()


# Dependency to get Redis client
async def get_redis_client() -> Redis:
    try:
        redis_client = Redis.from_url(
            "redis://localhost:6380  # Redis port updated from 6379 to 6380",
            decode_responses=True,
        )
        # Test connection
        await redis_client.ping()
        return redis_client
    except ConnectionError:
        raise HTTPException(status_code=503, detail="Redis service is unavailable")


# Middleware for tenant isolation
app.add_middleware(TenantMiddleware)


@app.get("/health")
async def health_check(redis: Redis = Depends(get_redis_client)):
    """
    Health check endpoint to verify Redis connectivity.
    Returns 200 OK if Redis is available, otherwise raises 503.
    """
    return {"status": "healthy"}


@app.get("/data")
async def get_data(key: str, redis: Redis = Depends(get_redis_client)):
    """
    Fetch data from Redis for the given key.
    Returns 503 if Redis is unavailable.
    """
    value = await redis.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"key": key, "value": value}


@app.post("/data")
async def set_data(key: str, value: str, redis: Redis = Depends(get_redis_client)):
    """
    Store data in Redis with the given key and value.
    Returns 503 if Redis is unavailable.
    """
    await redis.set(key, value)
    return {"status": "success", "key": key, "value": value}
