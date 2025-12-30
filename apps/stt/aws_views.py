# apps/stt/views.py
import os
import time
import uuid
import logging
import boto3
import requests  # Transcribe 결과 JSON URL fetch
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def stt_view(request):
    """
    AWS Transcribe(Batch)로 음성 -> 텍스트 전사 후 transcript 반환

    multipart/form-data:
      - file: 오디오 파일 (wav/mp3/webm 등)
      - (선택) language: 기본 ko-KR
    """
    audio_file = request.FILES.get("file")
    if not audio_file:
        return JsonResponse({"error": "missing file"}, status=400)

    region = os.getenv("CLOUD_AWS_REGION", "ap-northeast-2")
    bucket = os.getenv("STT_S3_BUCKET")
    if not bucket:
        return JsonResponse({"error": "STT_S3_BUCKET not set"}, status=500)

    # 추가: boto3 clients
    s3 = boto3.client("s3", region_name=region)
    transcribe = boto3.client("transcribe", region_name=region)

    # 추가: S3 업로드 (오디오)
    key = f"stt/audio/{uuid.uuid4()}_{audio_file.name}"
    s3.upload_fileobj(audio_file, bucket, key)
    media_uri = f"s3://{bucket}/{key}"

    # 추가: media format 추정 (안정적으로 가려면 프론트에서 wav로 통일 추천)
    ext = (audio_file.name.split(".")[-1] or "").lower()
    media_format = ext if ext in ["wav", "mp3", "mp4", "webm", "flac", "ogg"] else "wav"

    language = request.POST.get("language") or "ko-KR"  # 추가

    # 추가: Transcribe job 시작
    job_name = f"stt-{uuid.uuid4()}"
    transcribe.start_transcription_job(
        TranscriptionJobName=job_name,
        LanguageCode=language,
        MediaFormat=media_format,
        Media={"MediaFileUri": media_uri},
        OutputBucketName=bucket,  # 추가: 결과 JSON을 S3에 저장
        OutputKey=f"stt/result/{job_name}.json",  # 추가: 결과 파일 경로 고정(추적 쉬움)
    )

    # 추가: 완료까지 폴링 (PoC용. 운영이면 Celery/큐 권장)
    timeout_sec = 30  # 추가: PoC 타임아웃(짧은 음성 기준)
    start = time.time()

    status = "IN_PROGRESS"
    while True:
        resp = transcribe.get_transcription_job(TranscriptionJobName=job_name)
        status = resp["TranscriptionJob"]["TranscriptionJobStatus"]

        if status in ["COMPLETED", "FAILED"]:
            break

        if time.time() - start > timeout_sec:
            return JsonResponse({"error": "transcribe timeout"}, status=504)

        time.sleep(0.5)

    if status == "FAILED":
        logger.error("Transcribe failed: %s", resp)
        return JsonResponse({"error": "transcribe failed"}, status=500)

    # 추가: 결과 JSON 가져오기 (TranscriptFileUri는 presigned URL로 제공됨)
    transcript_uri = resp["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]

    r = requests.get(transcript_uri, timeout=10)
    r.raise_for_status()
    data = r.json()

    transcript = (data.get("results", {})
                    .get("transcripts", [{}])[0]
                    .get("transcript", "")).strip()

    # transcript 반환 (prompt_view 재사용은 프론트에서)
    return JsonResponse({
        "transcript": transcript,
        "jobName": job_name
    })
