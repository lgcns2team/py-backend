import os
import redis
from django.conf import settings

_redis_client = None

def _get_setting(name: str, default=None):
    return getattr(settings, name, os.getenv(name, default))

def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    
    redis_url = _get_setting("REDIS_URL", None)

    host = getattr(settings, "REDIS_HOST", os.getenv("REDIS_HOST", "localhost"))
    port = int(getattr(settings, "REDIS_PORT", os.getenv("REDIS_PORT", 6379)))
    db = int(getattr(settings, "REDIS_DB", os.getenv("REDIS_DB", 0)))
    password = _get_setting("REDIS_PASSWORD", None)

    if not redis_url:
        use_ssl = str(_get_setting("REDIS_SSL", "false")).lower() in ("1", "true", "yes", "y")
        scheme = "rediss" if use_ssl else "redis"
        redis_url = f"{scheme}://{host}:{port}/{db}"

    is_tls = redis_url.startswith("rediss://")

    kwargs = dict(
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )

    if password:
        kwargs["password"] = password

    if is_tls:
        kwargs["ssl_cert_reqs"] = None

    _redis_client = redis.Redis.from_url(redis_url, **kwargs)
    return _redis_client
