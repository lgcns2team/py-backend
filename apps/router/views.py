"""
Agent Chat Router Views
Tool Calling과 Knowledge Base 검색을 통합하는 라우터
"""
import json
import logging
import os
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from common.bedrock.converse import ConverseClient
from common.bedrock.clients import BedrockClients
from common.bedrock.streaming import sse_event
from apps.tools.definitions import TOOL_CONFIG, ROUTER_SYSTEM_PROMPT
from apps.tools.handlers import handle_tool_result

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def agent_chat_view(request):
    """
    Agent Router: Tool Calling 또는 Knowledge Base 검색으로 라우팅
    
    Request:
        {"message": "이순신한테 말걸어줘"} - Tool Call 트리거
        {"message": "조선시대 경제는?"} - Knowledge Base 검색
    
    Response (Tool Call):
        {"type": "tool_call", "action": "navigate_to_person", "input": {"person_name": "이순신"}}
    
    Response (Knowledge Base):
        SSE 스트리밍 응답
    """
    try:
        data = json.loads(request.body)
        query = data.get('message') or data.get('query')
        
        if not query:
            return JsonResponse({
                'type': 'error',
                'message': 'Missing required field: message'
            }, status=400)
        
        logger.info(f"Agent Chat 요청: {query[:50]}...")
        
        # 1단계: Converse API로 Intent Detection
        converse_client = ConverseClient()
        result = converse_client.invoke_with_tools(
            messages=[{
                "role": "user",
                "content": [{"text": query}]
            }],
            tool_config=TOOL_CONFIG,
            system=[{"text": ROUTER_SYSTEM_PROMPT}]
        )
        
        # 2단계: 라우팅
        if result['type'] == 'tool_call':
            action = result['action']
            tool_input = result['input']
            
            logger.info(f"Tool Call 감지: {action}")

            # [CASE A] 전쟁 툴인 경우 -> 스트리밍 (Tool + KB 답변)
            if action == "navigate_to_war":
                return StreamingHttpResponse(
                    stream_war_navigation_and_kb(query, tool_input),
                    content_type='text/event-stream'
                )

            # [CASE B] 일반 툴인 경우 -> JSON 응답
            tool_response = handle_tool_result(action, tool_input)
            return JsonResponse(tool_response)

        else:
            # 일반 질문 - Knowledge Base 검색으로 Fallback
            logger.info("Knowledge Base 검색으로 Fallback")
            return knowledge_base_streaming_response(query)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'type': 'error',
            'message': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        logger.error(f"Agent Chat 오류: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({
            'type': 'error',
            'message': str(e)
        }, status=500)



def knowledge_base_streaming_response(query: str):
    """Knowledge Base 스트리밍 검색 응답"""
    try:
        kb_id = os.getenv('AWS_BEDROCK_KB_ID')
        model_arn = os.getenv('AWS_BEDROCK_KB_MODEL_ARN')
        
        if not kb_id or not model_arn:
            return JsonResponse({
                'type': 'error',
                'message': 'Knowledge Base not configured'
            }, status=500)
        
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
            stream_kb_response(response),
            content_type='text/event-stream'
        )
        
    except Exception as e:
        logger.error(f"Knowledge Base 오류: {str(e)}")
        return StreamingHttpResponse(
            [sse_event({'type': 'error', 'message': str(e)})],
            content_type='text/event-stream'
        )


def stream_kb_response(response):
    """Knowledge Base 스트리밍 응답 처리"""
    citations = []
    
    try:
        for event in response['stream']:
            if 'output' in event:
                output_data = event['output']
                if 'text' in output_data:
                    text = output_data['text']
                    yield sse_event({'type': 'content', 'text': text})
            
            elif 'citation' in event:
                citations.append(event['citation'])
        
        if citations:
            yield sse_event({
                'type': 'citations',
                'count': len(citations),
                'data': citations
            })
        
        yield sse_event({'type': 'done'})
        
    except Exception as e:
        logger.error(f"스트리밍 오류: {str(e)}")
        yield sse_event({'type': 'error', 'message': str(e)})


def stream_war_navigation_and_kb(query, tool_params):
    """
    1. 툴 호출 이벤트 전송 (navigate_to_war)
    2. KB 검색 결과 스트리밍 전송
    """
    # 1. Tool Call 먼저 전송 (프론트엔드가 지도 이동 시작)
    yield sse_event({
        "type": "tool_call",
        "tool_name": "navigate_to_war",
        "parameters": {
            "year": tool_params.get('year'),
            "war_name": tool_params.get('war_name')
        }
    })

    # 2. KB 검색 시작 (사용자 질문으로 답변 생성)
    # 기존 knowledge_base_streaming_response 로직 재사용
    try:
        kb_id = os.getenv('BEDROCK_KB_ID')
        model_arn = os.getenv('BEDROCK_KB_MODEL_ARN')
        
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
        
        # KB 응답 스트리밍 (stream_kb_response 재사용)
        # 주의: stream_kb_response는 'done' 이벤트를 마지막에 보내므로, 
        # 여기서는 그대로 yield from 해도 됩니다.
        yield from stream_kb_response(response)
        
    except Exception as e:
        logger.error(f"KB Stream Error: {e}")
        yield sse_event({'type': 'error', 'message': str(e)})