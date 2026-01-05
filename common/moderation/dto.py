from dataclasses import dataclass
from typing import Optional

@dataclass
class ModerationResult:
    allowed: bool
    muted: bool
    content: Optional[str]
    notice: Optional[str]
    mute_seconds_left: int
