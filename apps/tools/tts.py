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
import torch
import logging
import subprocess
import scipy.io.wavfile
from django.conf import settings
from transformers import VitsModel, AutoTokenizer

logger = logging.getLogger(__name__)

# 1. 가이드 음성용 모델 (Hugging Face)
MODEL_NAME = "facebook/mms-tts-kor"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
hf_model = VitsModel.from_pretrained(MODEL_NAME)

def generate_tts_file(text, voice_id=None):
    if not text: return None

    base_dir = settings.BASE_DIR # py-backend 루트
    temp_dir = os.path.join(base_dir, 'media', 'tts')
    os.makedirs(temp_dir, exist_ok=True)
    
    # 파일 경로들
    guid_file = os.path.join(temp_dir, f"guid_{uuid.uuid4().hex}.wav")  # 남자 목소리 (임시)
    final_file = os.path.join(temp_dir, f"tts_{uuid.uuid4().hex}.wav")  # 카리나 목소리 (최종)
    
    try:
        # 1. 일단 허깅페이스로 "남자 목소리" 가이드 파일을 만듭니다.
        inputs = tokenizer(text, return_tensors="pt")
        with torch.no_grad():
            output = hf_model(**inputs).waveform
        scipy.io.wavfile.write(guid_file, rate=hf_model.config.sampling_rate, data=output.squeeze().numpy())

        # 2. [수정 포인트] 경로 설정
        # 이제 ttsSample이 py-backend 안에 있으므로 아래와 같이 잡습니다.
        rvc_python_path = sys.executable  # 현재 장고 가상환경의 파이썬 경로를 자동으로 잡음
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
            "--f0_up_key", "12"
        ], cwd=base_dir,
            env=current_env,
            check=True,
            capture_output=True,
            text=True) # cwd를 base_dir로 설정

        if os.path.exists(guid_file):
            os.remove(guid_file)

        return final_file

    except Exception as e:
        if hasattr(e, 'stderr'):
            logger.error(f"RVC 상세 에러 내용:\n{e.stderr}")
        logger.error(f"RVC 변환 실패 원인: {str(e)}")
        return None  # 실패하면 아무것도 주지 않음 (Internal Server Error가 나게 해서 디버깅)