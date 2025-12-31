# import boto3
# import os
# import uuid
# from django.conf import settings
# import logging

# logger = logging.getLogger(__name__)

# def generate_tts_file(text, voice_id):
#     polly = boto3.client('polly', region_name='ap-northeast-2')
    
#     ssml_text = f"""
#     <speak>
#         <amazon:auto-breaths volume="soft" frequency="low">
#             <prosody rate="92%" pitch="-9%">
#                 {text}
#             </prosody>
#         </amazon:auto-breaths>
#     </speak>
#     """
    
    
    
#     temp_dir = os.path.join(settings.BASE_DIR, 'media', 'tts')
#     if not os.path.exists(temp_dir):
#         os.makedirs(temp_dir)
        
#     file_name = f"tts_{uuid.uuid4().hex}.mp3"
#     file_path = os.path.join(temp_dir, file_name)
    
#     try:
#         # Polly API 호출
#         response = polly.synthesize_speech(
#             Text=ssml_text,
#             TextType='ssml',
#             OutputFormat='mp3',
#             VoiceId=voice_id,
#             Engine='standard'
#         )

#         # 오디오 스트림을 파일로 저장
#         if "AudioStream" in response:
#             with open(file_path, "wb") as f:
#                 f.write(response["AudioStream"].read())
            
#             logger.info(f"TTS 파일 생성 성공: {file_path} (Voice: {voice_id})")
#             return file_path
#         else:
#             logger.error("Polly 응답에 AudioStream이 없습니다.")
#             return None

#     except Exception as e:
#         logger.error(f"Amazon Polly TTS 생성 중 오류 발생: {str(e)}")
#         return None
import sys
import os
import uuid
import logging
import subprocess
from django.conf import settings

logger = logging.getLogger(__name__)

def generate_tts_file(text, voice_id=None):
    if not text: return None

    base_dir = settings.BASE_DIR # py-backend 루트
    temp_dir = os.path.join(base_dir, 'media', 'tts')
    os.makedirs(temp_dir, exist_ok=True)
    
    # 파일 경로들
    guid_file = os.path.join(temp_dir, f"guid_{uuid.uuid4().hex}.wav")  # Edge-TTS 여성 목소리 (임시)
    final_file = os.path.join(temp_dir, f"tts_{uuid.uuid4().hex}.wav")  # 카리나 목소리 (최종)
    
    try:
        # 1. Edge-TTS로 자연스러운 한국어 여성 목소리 가이드 파일 생성
        import asyncio
        import edge_tts
        
        async def create_base_tts():
            # ko-KR-SunHiNeural: 한국어 여성 목소리 (자연스러운 발음)
            communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
            await communicate.save(guid_file)
        
        # asyncio 이벤트 루프 실행
        asyncio.run(create_base_tts())

        # 2. [수정 포인트] 경로 설정
        # ttsSample은 Python 3.10이 필요하므로 ttsSample의 가상환경 사용
        rvc_python_path = os.path.join(base_dir, "ttsSample", ".venv", "Scripts", "python.exe")
        rvc_main_path = os.path.join(base_dir, "ttsSample", "main.py")
        
        # 모델 파일은 py-backend/models/ 안에 있다고 가정
        model_path = os.path.join(base_dir, "models", "Karina_KLMx9.pth")
        index_path = os.path.join(base_dir, "models", "added_Karina_KLMx9.index")

        current_env = os.environ.copy()
        current_env["HYDRA_FULL_ERROR"] = "0"  # 디버깅용
        # 3. RVC 실행 (cwd 설정을 추가해서 main.py 내부 상대경로 에러 방지)
        result = subprocess.run([
            rvc_python_path, rvc_main_path,
            "--input", guid_file,
            "--model", model_path,
            "--index", index_path,
            "--output", final_file,
            "--f0_up_key", "-6"
        ], cwd=base_dir,
            env=current_env,
            check=True,
            capture_output=False,
            text=True) # cwd를 base_dir로 설정

        if os.path.exists(guid_file):
            os.remove(guid_file)

        return final_file

    except Exception as e:
        if hasattr(e, 'stderr'):
            logger.error(f"RVC 상세 에러 내용:\n{e.stderr}")
        logger.error(f"RVC 변환 실패 원인: {str(e)}")
        return None  # 실패하면 아무것도 주지 않음 (Internal Server Error가 나게 해서 디버깅)