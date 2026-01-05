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
import boto3
import os
import uuid
import logging
import subprocess
from django.conf import settings
from contextlib import closing

def generate_tts_file(text, voice_id='Seoyeon'):
    """Amazon Polly를 사용하여 mp3 파일 저장"""
    polly_client = boto3.client('polly', region_name='ap-northeast-2')
    
    try:
        response = polly_client.synthesize_speech(
            Text=text,
            OutputFormat='mp3',
            VoiceId=voice_id,
            Engine='neural'
        )

        file_path = f"/tmp/tts_{voice_id}.mp3" # 혹은 적절한 미디어 경로
        
        if "AudioStream" in response:
            with closing(response["AudioStream"]) as stream:
                with open(file_path, "wb") as f:
                    f.write(stream.read())
            return file_path
    except Exception as e:
        print(f"Polly Error: {e}")
        return None