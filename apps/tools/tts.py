import boto3
import os
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