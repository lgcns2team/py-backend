from django.conf import settings
from django.core.cache import cache
from .dto import ModerationResult
from .regex_loader import build_profanity_regex

BAD_RX = build_profanity_regex()

def _warn_key(user_id: str) -> str:
    return f"moderation:warn:{user_id}"

def _mute_key(user_id: str) -> str:
    return f"moderation:mute:{user_id}"

def check(user_id: str, incoming: str) -> ModerationResult:
    warn_ttl = getattr(settings, "MODERATION_WARN_TTL_SECONDS", 86400)
    mute_seconds = getattr(settings, "MODERATION_MUTE_SECONDS", 300)

    mk = _mute_key(user_id)
    if cache.get(mk):
        # TTL 조회(지원 안 되면 mute_seconds로)
        ttl = mute_seconds
        if hasattr(cache, "ttl"):
            try:
                t = cache.ttl(mk)
                if isinstance(t, int) and t > 0:
                    ttl = t
            except Exception:
                pass

        return ModerationResult(
            allowed=False,
            muted=True,
            content=None,
            notice="현재 채팅이 5분간 제한되었습니다.",
            mute_seconds_left=ttl,
        )

    text = incoming or ""
    hit = bool(BAD_RX.search(text))
    if not hit:
        return ModerationResult(True, False, text, None, 0)

    wk = _warn_key(user_id)
    warn = cache.get(wk, 0) + 1
    cache.set(wk, warn, timeout=warn_ttl)

    if warn == 1:
        masked = BAD_RX.sub("***", text)
        return ModerationResult(
            allowed=True,
            muted=False,
            content=masked,
            notice="비속어/부적절한 표현이 감지되어 일부가 마스킹되었습니다. 표현을 정제해 주세요.",
            mute_seconds_left=0,
        )

    cache.set(mk, "1", timeout=mute_seconds)
    return ModerationResult(
        allowed=False,
        muted=True,
        content=None,
        notice="비속어/부적절한 표현이 반복되어 5분간 채팅이 제한됩니다.",
        mute_seconds_left=mute_seconds,
    )
