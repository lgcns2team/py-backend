# Whisper STT 서비스
import whisper

# 서버 프로세스에서 1회만 로드되도록 전역 싱글톤 사용
_WHISPER_MODEL = None

def get_model():
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        # POC 권장: base (속도/성능 균형)
        _WHISPER_MODEL = whisper.load_model("base")
    return _WHISPER_MODEL

def transcribe_audio(file_path: str, language: str = "ko") -> str:
    model = get_model()
    result = model.transcribe(file_path, language=language)
    return (result.get("text") or "").strip()
