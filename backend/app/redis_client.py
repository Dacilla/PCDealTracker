import json

import redis

from .config import settings


_redis_client = None


def _get_client():
    global _redis_client

    if not settings.cache_enabled:
        return None

    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def get_cache(key):
    client = _get_client()
    if client is None:
        return None

    try:
        cached_data = client.get(key)
        if cached_data:
            return json.loads(cached_data)
    except redis.exceptions.RedisError as exc:
        print(f"Redis GET error: {exc}")
    return None


def set_cache(key, value, expiry_seconds=3600):
    client = _get_client()
    if client is None:
        return

    try:
        client.setex(key, expiry_seconds, json.dumps(value, default=str))
    except redis.exceptions.RedisError as exc:
        print(f"Redis SET error: {exc}")


def clear_all_cache():
    client = _get_client()
    if client is None:
        return

    try:
        client.flushdb()
        print("--- Redis Cache Cleared ---")
    except redis.exceptions.RedisError as exc:
        print(f"Redis FLUSHDB error: {exc}")
