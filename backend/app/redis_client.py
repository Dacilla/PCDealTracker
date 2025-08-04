import redis
import json
from .config import settings

# Initialize the Redis client from the settings URL
# decode_responses=True ensures that we get strings back from Redis, not bytes.
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

def get_cache(key):
    """Gets a value from the cache."""
    try:
        cached_data = redis_client.get(key)
        if cached_data:
            return json.loads(cached_data)
    except redis.exceptions.RedisError as e:
        print(f"Redis GET error: {e}")
    return None

def set_cache(key, value, expiry_seconds=3600):
    """Sets a value in the cache with an expiry time (default 1 hour)."""
    try:
        redis_client.setex(key, expiry_seconds, json.dumps(value, default=str))
    except redis.exceptions.RedisError as e:
        print(f"Redis SET error: {e}")


def clear_all_cache():
    """Clears the entire Redis cache."""
    try:
        redis_client.flushdb()
        print("--- Redis Cache Cleared ---")
    except redis.exceptions.RedisError as e:
        print(f"Redis FLUSHDB error: {e}")
