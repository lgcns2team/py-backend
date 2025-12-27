import json
from typing import List, Dict, Any

from common.redis.redis_client import get_redis_client

def load_debate_messages(room_id: str) -> List[Dict[str, Any]]:
    
    r = get_redis_client()
    key = f"debate:room:{room_id}:messages"

    raw_list = r.lrange(key, 0, -1)  # 전체
    if not raw_list:
        return []

    msgs = []
    for raw in raw_list:
        try:
            msgs.append(json.loads(raw))
        except Exception:
            continue
    return msgs
