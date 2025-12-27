# from gtts import gTTS
# import os
# from django.conf import settings
# import uuid;

# def generate_tts_file(text):
#     """텍스트를 받아 mp3 파일을 생성하고 저장 경로를 반환"""
    
#     # media 폴더가 없다면 생성 (보통 장고 프로젝트 루트의 media 폴더)
#     temp_dir = os.path.join(settings.BASE_DIR, 'media', 'tts')
#     if not os.path.exists(temp_dir):
#         os.makedirs(temp_dir)

#     # 파일명이 겹치지 않게 고유한 ID(uuid)를 사용합니다
#     file_name = f"tts_{uuid.uuid4().hex}.mp3"
#     file_path = os.path.join(temp_dir, file_name)
    
#     # gTTS 실행
#     tts = gTTS(text=text, lang='ko')
#     tts.save(file_path)
    
#     return file_path

import boto3
import os
import uuid
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def generate_tts_file(text, voice_id):
    polly = boto3.client('polly', region_name='ap-northeast-2')
    
    ssml_text = f"""
    <speak>
        <amazon:auto-breaths volume="soft" frequency="low">
            <prosody rate="92%" pitch="-9%">
                {text}
            </prosody>
        </amazon:auto-breaths>
    </speak>
    """
    
    
    
    temp_dir = os.path.join(settings.BASE_DIR, 'media', 'tts')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        
    file_name = f"tts_{uuid.uuid4().hex}.mp3"
    file_path = os.path.join(temp_dir, file_name)
    
    try:
        # Polly API 호출
        response = polly.synthesize_speech(
            Text=ssml_text,
            TextType='ssml',
            OutputFormat='mp3',
            VoiceId=voice_id,
            Engine='standard'
        )

        # 오디오 스트림을 파일로 저장
        if "AudioStream" in response:
            with open(file_path, "wb") as f:
                f.write(response["AudioStream"].read())
            
            logger.info(f"TTS 파일 생성 성공: {file_path} (Voice: {voice_id})")
            return file_path
        else:
            logger.error("Polly 응답에 AudioStream이 없습니다.")
            return None

    except Exception as e:
        logger.error(f"Amazon Polly TTS 생성 중 오류 발생: {str(e)}")
        return None