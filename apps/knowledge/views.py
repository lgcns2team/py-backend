import json
import logging
import os
import requests
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from common.bedrock.clients import BedrockClients
from common.bedrock.streaming import sse_event
from rest_framework.decorators import api_view

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def knowledge_base_view(request):
    """Knowledge Base 검색 (스트리밍)"""
    try:
        data = json.loads(request.body)
        
        query = data.get('message') or data.get('query')
        
        if not query:
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': 'Missing required field: message or query'})],
                content_type='text/event-stream'
            )
        
        # ✅ .env 파일의 실제 변수명 사용
        kb_id = data.get('kb_id') or os.getenv('BEDROCK_KB_ID')
        model_arn = data.get('model_arn') or os.getenv('BEDROCK_KB_MODEL_ARN')
        
        if not kb_id or not model_arn:
            logger.error(f"Missing config - KB_ID: {kb_id}, MODEL_ARN: {model_arn}")
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': f'KB_ID or MODEL_ARN not configured. KB_ID={kb_id}, MODEL_ARN={model_arn}'})],
                content_type='text/event-stream'
            )
        
        logger.info(f"KB request - KB ID: {kb_id}, Query: {query[:50]}...")
        
        bedrock_agent_runtime = BedrockClients.get_agent_runtime()
        response = bedrock_agent_runtime.retrieve_and_generate_stream(
            input={'text': query},
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': kb_id,
                    'modelArn': model_arn
                }
            }
        )
        
        return StreamingHttpResponse(
            stream_knowledge_base_response(response),
            content_type='text/event-stream'
        )
        
    except Exception as e:
        logger.error(f"KB error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return StreamingHttpResponse(
            [sse_event({'type': 'error', 'message': str(e)})],
            content_type='text/event-stream'
        )

def stream_knowledge_base_response(response):
    """Knowledge Base 스트리밍 응답"""
    citations = []
    full_text = ""
    
    try:
        for event in response['stream']:
            if 'output' in event:
                output_data = event['output']
                if 'text' in output_data:
                    text = output_data['text']
                    full_text += text
                    yield sse_event({'type': 'content', 'text': text})
                    logger.info(f"Sent text chunk: {text[:30]}...")
            
            elif 'citation' in event:
                citation_data = event['citation']
                citations.append(citation_data)
                logger.info("Citation received")
        
        if citations:
            logger.info(f"Sending {len(citations)} citations")
            yield sse_event({
                'type': 'citations',
                'count': len(citations),
                'data': citations
            })
        
        logger.info(f"Stream complete. Total text length: {len(full_text)}")
        yield sse_event({'type': 'done', 'total_length': len(full_text)})
        
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield sse_event({'type': 'error', 'message': str(e)})

@csrf_exempt
@api_view(["POST"])
def chatbot_tts_view(request):
    """일반 AI 챗봇 전용 TTS (DB 연동 없음)"""
    try:
        text = request.data.get('text', '')
        if not text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        # ✅ 챗봇 전용 목소리 ID 직접 지정 (원하는 ID로 변경 가능)
        voice_id = 'tc_630494521f5003bebbfdafef' 

        typecast_api_key = os.getenv('TYPECAST_API_KEY')
        url = "https://api.typecast.ai/v1/text-to-speech"
        
        headers = {
            "X-API-KEY": typecast_api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text,
            "voice_id": voice_id,
            "language": "ko",
            "model": "ssfm-v21",
            "output": {"audio_format": "mp3"}
        }

        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            return StreamingHttpResponse(
                iter([response.content]), 
                content_type='audio/mpeg'
            )
        else:
            return JsonResponse({'error': 'Typecast 호출 실패'}, status=response.status_code)

    except Exception as e:
        logger.error(f"Chatbot TTS Error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)