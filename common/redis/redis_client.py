import os
import redis
from django.conf import settings

_redis_client = None

def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    # redis_url = getattr(settings, "REDIS_URL", None) or os.getenv("REDIS_URL")

    # if redis_url:
    #     _redis_client = redis.Redis.from_url(
    #         redis_url,
    #         decode_responses=True,
    #         ssl_cert_reqs=None,
    #         socket_connect_timeout=5,
    #         socket_timeout=5,
    #         retry_on_timeout=True,
    #     )
    #     return _redis_client

    host = getattr(settings, "REDIS_HOST", os.getenv("REDIS_HOST", "localhost"))
    port = int(getattr(settings, "REDIS_PORT", os.getenv("REDIS_PORT", 6379)))
    db = int(getattr(settings, "REDIS_DB", os.getenv("REDIS_DB", 0)))

    # url = f"rediss://{host}:{port}/{db}"

    _redis_client = redis.Redis(
            host,
            port,
            db,
    )

    # _redis_client = redis.Redis.from_url(
    #     url,
    #     decode_responses=True,
    #     ssl_cert_reqs=None,
    #     socket_connect_timeout=5,
    #     socket_timeout=5,
    #     retry_on_timeout=True,
    # )
    return _redis_client
