import uuid

VOICE_PREFIX = "voice"

def build_voice_key(user_id: str, session_id: str, ext: str = "m4a") -> str:
    """
    voice/{user_id}/{session_id}/{uuid}.m4a 형태로 key 생성
    """
    safe_user = user_id or "anonymous"
    safe_session = session_id or "default"
    file_id = str(uuid.uuid4())
    return f"{VOICE_PREFIX}/{safe_user}/{safe_session}/{file_id}.{ext.lstrip('.')}"