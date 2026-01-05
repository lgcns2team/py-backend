import re
import logging
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)

def _load_patterns(file_path: Path) -> List[str]:
    if not file_path.exists():
        log.error("Regex file missing: %s", file_path)
        return []

    lines = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        if re.fullmatch(r"=+", s):
            continue
        lines.append(s)
    return lines

def build_profanity_regex() -> re.Pattern:
    base_dir = Path(__file__).resolve().parent
    patterns_dir = base_dir / "patterns"

    patterns = []
    patterns += _load_patterns(patterns_dir / "profanity_base.regex")
    patterns += _load_patterns(patterns_dir / "profanity_evasion.regex")

    if not patterns:
        log.error("No profanity patterns loaded. Moderation disabled!")
        return re.compile(r"a^")

    joined = "|".join(f"(?:{p})" for p in patterns)

    try:
        return re.compile(joined, re.UNICODE | re.IGNORECASE)
    except re.error:
        log.exception("Profanity regex compile failed. Moderation disabled!")
        return re.compile(r"a^")
