import os
import tempfile
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from .services.s3_service import S3Service
from .services.key_builder import build_voice_key
from .services.whisper_service import transcribe_audio

@csrf_exempt  # POC 단계에서만. 운영에서는 Gateway/CSRF 전략에 맞춰 조정
@require_POST
def presign_voice_upload(request):
    """
    1) 프론트가 S3로 직접 업로드할 수 있도록 presigned PUT URL 발급
    request JSON:
      {
        "user_id": "uuid-or-string",
        "session_id": "chat-session-id",
        "ext": "m4a",
        "content_type": "audio/mp4"  (m4a 보통 audio/mp4)
      }
    response:
      { "key": "...", "upload_url": "..." }
    """
    import json
    body = json.loads(request.body or "{}")

    user_id = body.get("user_id") or "anonymous"
    session_id = body.get("session_id") or "default"
    ext = body.get("ext") or "m4a"
    content_type = body.get("content_type") or "audio/mp4"

    key = build_voice_key(user_id=user_id, session_id=session_id, ext=ext)  # ✅ [신규] voice/ prefix 적용
    s3 = S3Service()
    upload_url = s3.create_presigned_put_url(key=key, content_type=content_type, expires_in=300)

    return JsonResponse({
        "key": key,
        "upload_url": upload_url,
        "expires_in": 300,
    })

@csrf_exempt  # POC 단계에서만
@require_POST
def stt_from_s3_key(request):
    """
    2) S3에 업로드된 음성 파일 key를 받아 Whisper STT 수행
    request JSON:
      { "key": "voice/..../xxx.m4a", "language": "ko" }
    response:
      { "ok": true, "text": "...", "key": "...", "uploaded": true }
    """
    import json
    body = json.loads(request.body or "{}")
    key = body.get("key")
    language = body.get("language") or "ko"

    if not key:
        return JsonResponse({"ok": False, "error": "key is required"}, status=400)

    # prefix 방어: voice/ 아래만 허용 (교과서 prefix와 분리)
    if not key.startswith("voice/"):
        return JsonResponse({"ok": False, "error": "invalid key prefix (must start with voice/)"}, status=400)

    s3 = S3Service()

    # 업로드 되었는지 확인 (head_object)
    try:
        s3.head_object(key)
        uploaded = True
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"s3 object not found or not accessible: {str(e)}"}, status=404)

    # 임시 파일로 다운로드 후 whisper 처리
    tmp_dir = tempfile.mkdtemp(prefix="stt_")
    local_path = os.path.join(tmp_dir, os.path.basename(key))

    try:
        s3.download_to_file(key=key, local_path=local_path)
        text = transcribe_audio(local_path, language=language)
        return JsonResponse({
            "ok": True,
            "key": key,
            "uploaded": uploaded,
            "text": text,
        })
    finally:
        # 임시파일 정리
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
            os.rmdir(tmp_dir)
        except Exception:
            pass
