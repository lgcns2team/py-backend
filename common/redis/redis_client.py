import os
import redis
from django.conf import settings
from urllib.parse import urlparse

_redis_client = None

def get_redis_client() -> redis.Redis:
    """
    Redis 클라이언트 싱글톤 반환
    REDIS_URL 우선 사용, 없으면 개별 설정 사용
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    
    # REDIS_URL 우선 확인
    redis_url = getattr(settings, 'REDIS_URL', None) or os.getenv('REDIS_URL')
    
    # REDIS_URL이 있으면 파싱해서 사용
    if redis_url:
        url = urlparse(redis_url)
        is_ssl = url.scheme == 'rediss'
        
        kwargs = {
            'decode_responses': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
            'retry_on_timeout': True,
        }
        
        # SSL 설정 (rediss://인 경우)
        if is_ssl:
            kwargs['ssl_cert_reqs'] = None  # ElastiCache는 인증서 검증 안 함
        
        # 비밀번호가 URL에 있으면 자동으로 처리됨
        _redis_client = redis.Redis.from_url(redis_url, **kwargs)
    
    else:
        # REDIS_URL이 없으면 개별 설정 사용
        host = getattr(settings, 'REDIS_HOST', os.getenv('REDIS_HOST', 'localhost'))
        port = int(getattr(settings, 'REDIS_PORT', os.getenv('REDIS_PORT', 6379)))
        db = int(getattr(settings, 'REDIS_DB', os.getenv('REDIS_DB', 0)))
        password = getattr(settings, 'REDIS_PASSWORD', os.getenv('REDIS_PASSWORD', None))
        use_ssl = str(getattr(settings, 'REDIS_SSL', os.getenv('REDIS_SSL', 'false'))).lower() in ('1', 'true', 'yes')
        
        kwargs = {
            'host': host,
            'port': port,
            'db': db,
            'decode_responses': True,
            'socket_connect_timeout': 5,
            'socket_timeout': 5,
            'retry_on_timeout': True,
        }
        
        if password:
            kwargs['password'] = password
        
        if use_ssl:
            kwargs['ssl'] = True
            kwargs['ssl_cert_reqs'] = None
        
        _redis_client = redis.Redis(**kwargs)
    
    return _redis_client


def test_redis_connection():
    """Redis 연결 테스트"""
    try:
        client = get_redis_client()
        client.ping()
        
        redis_url = getattr(settings, 'REDIS_URL', None) or os.getenv('REDIS_URL')
        if redis_url:
            print(f"✅ Redis 연결 성공 (URL: {redis_url[:20]}...)")
        else:
            host = getattr(settings, 'REDIS_HOST', 'localhost')
            port = getattr(settings, 'REDIS_PORT', 6379)
            print(f"✅ Redis 연결 성공 ({host}:{port})")
        
        return True
    except Exception as e:
        print(f"❌ Redis 연결 실패: {e}")
        return False


# 모듈 로드 시 연결 테스트 (선택사항)
if __name__ == '__main__':
    test_redis_connection()