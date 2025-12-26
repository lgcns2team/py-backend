from gtts import gTTS
import os
from django.conf import settings
import uuid;

def generate_tts_file(text):
    """텍스트를 받아 mp3 파일을 생성하고 저장 경로를 반환"""
    
    # media 폴더가 없다면 생성 (보통 장고 프로젝트 루트의 media 폴더)
    temp_dir = os.path.join(settings.BASE_DIR, 'media', 'tts')
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    # 파일명이 겹치지 않게 고유한 ID(uuid)를 사용합니다
    file_name = f"tts_{uuid.uuid4().hex}.mp3"
    file_path = os.path.join(temp_dir, file_name)
    
    # gTTS 실행
    tts = gTTS(text=text, lang='ko')
    tts.save(file_path)
    
    return file_path