import json
import logging
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from common.bedrock.clients import BedrockClients
from common.bedrock.streaming import stream_bedrock_response, sse_event

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def chat_view(request):
    """AI 채팅 (스트리밍)"""
    try:
        data = json.loads(request.body)
        
        # ✅ 'message' 필드를 'messages' 배열로 변환
        if 'message' in data:
            user_message = data['message']
            messages = [{"role": "user", "content": user_message}]
        elif 'messages' in data:
            messages = data['messages']
        else:
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': 'Missing required fields: message or messages'})],
                content_type='text/event-stream'
            )
        
        model = data.get('model', 'anthropic.claude-3-5-sonnet-20240620-v1:0')
        max_tokens = data.get('max_tokens', 4096)
        temperature = data.get('temperature', 1.0)
        system = data.get('system')
        
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages
        }
        
        if system:
            body["system"] = system
        
        logger.info(f"Chat request - Model: {model}, Message: {messages[0]['content'][:50]}...")
        
        bedrock_runtime = BedrockClients.get_runtime()
        response = bedrock_runtime.invoke_model_with_response_stream(
            modelId=model,
            body=json.dumps(body)
        )
        
        return StreamingHttpResponse(
            stream_bedrock_response(response),
            content_type='text/event-stream'
        )
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return StreamingHttpResponse(
            [sse_event({'type': 'error', 'message': str(e)})],
            content_type='text/event-stream'
        )