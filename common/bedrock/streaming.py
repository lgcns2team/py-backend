import json
import logging

logger = logging.getLogger(__name__)

def sse_event(data: dict) -> str:
    """SSE 형식으로 데이터 포맷"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

def stream_bedrock_response(response):
    """Bedrock 스트리밍 응답 처리"""
    try:
        for event in response['body']:
            chunk = json.loads(event['chunk']['bytes'])
            
            if chunk['type'] == 'content_block_delta':
                text = chunk['delta'].get('text', '')
                if text:
                    yield sse_event({'type': 'content', 'text': text})
            
            elif chunk['type'] == 'message_stop':
                yield sse_event({'type': 'done'})
                break
                
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield sse_event({'type': 'error', 'message': str(e)})