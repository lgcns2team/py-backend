import json
from datetime import timedelta
from typing import List, Optional, Set
from uuid import UUID

import redis
from django.conf import settings

from .dto import MessageDTO
from common.redis.redis_client import get_redis_client


DEFAULT_TTL = timedelta(hours=6)

class RedisChatRepository:
    def __init__(self):
        self.redis = get_redis_client()

    # key에 해당하는 전체 메시지 히스토리 조회
    def get_messages(self, key: str) -> List[MessageDTO]:
        raw_list = self.redis.lrange(key, 0, -1)
        if not raw_list:
            return []
        return [self._deserialize(x) for x in raw_list]

    # 메시지 1개 추가
    def append_message(self, key: str, message: MessageDTO):
        self.append_message_with_ttl(key, message, DEFAULT_TTL)

    # 메시지 1개 추가 (TTL 지정)
    def append_message_with_ttl(self, key: str, message: MessageDTO, ttl: Optional[timedelta]):
        json_str = self._serialize(message)
        self.redis.rpush(key, json_str)
        if ttl is not None:
            self.redis.expire(key, int(ttl.total_seconds()))

    # 특정 key의 히스토리 삭제
    def delete_by_key(self, key: str):
        self.redis.delete(key)

    # 패턴으로 여러 키 삭제
    def delete_by_pattern(self, pattern: str):
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)

    def delete_all_aiperson_chats(self, user_id: UUID):
        pattern = f"aiperson:chat:*:{user_id}"
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)
            print(f"[REDIS] Deleted {len(keys)} AI Person chat keys for user: {user_id}")

    def delete_all_chatbot_chats(self, user_id: UUID):
        pattern = f"chatbot:chat:{user_id}"
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)
            print(f"[REDIS] Deleted {len(keys)} chatbot chat keys for user: {user_id}")

    def build_aiperson_key(self, prompt_id: str, user_id: UUID) -> str:
        return f"aiperson:chat:{prompt_id}:{user_id}"

    def _serialize(self, message: MessageDTO) -> str:
        try:
            return json.dumps(message.to_dict(), ensure_ascii=False)
        except Exception as e:
            raise RuntimeError("Redis 직렬화 실패") from e

    def _deserialize(self, json_str: str) -> MessageDTO:
        try:
            return MessageDTO.from_dict(json.loads(json_str))
        except Exception as e:
            raise RuntimeError("Redis 역직렬화 실패") from e
