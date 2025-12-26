import json
import logging
import os
import boto3
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from common.bedrock.clients import BedrockClients
from common.bedrock.streaming import sse_event


# apps/prompt/views.py 상단에 추가
from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework.decorators import api_view
from rest_framework import serializers
from django.http import JsonResponse, FileResponse
from apps.tools.tts import generate_tts_file
logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def prompt_view(request, promptId=None):
    """Bedrock Prompt 호출 (스트리밍) - FastAPI 로직 포팅"""
    try:
        data = json.loads(request.body)
        
        # promptId는 URL에서, user_query는 body에서
        prompt_id = promptId or data.get('prompt_id')
        user_query = data.get('message') or data.get('user_query')
        
        if not prompt_id or not user_query:
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': 'Missing prompt_id or message'})],
                content_type='text/event-stream'
            )
        
        variables = data.get('variables', {})
        
        logger.info(f"Prompt request - Prompt ID: {prompt_id}, Query: {user_query[:50]}...")
        
        # Bedrock Agent 클라이언트
        bedrock_agent = boto3.client(
            service_name='bedrock-agent',
            region_name=os.getenv('CLOUD_AWS_REGION', 'ap-northeast-2')
        )
        
        # ✅ FastAPI와 동일한 로직: ARN 구성 (버전 없음!)
        if prompt_id.startswith('arn:'):
            prompt_identifier = prompt_id
        else:
            # ✅ 버전 없이 ARN 구성
            prompt_identifier = f"arn:aws:bedrock:{os.getenv('CLOUD_AWS_REGION', 'ap-northeast-2')}:811221506617:prompt/{prompt_id}"
        
        logger.info(f"Using Prompt ARN: {prompt_identifier}")
        
        try:
            # Prompt 가져오기
            prompt_response = bedrock_agent.get_prompt(
                promptIdentifier=prompt_identifier
            )
            
            logger.info(f"Prompt retrieved: {prompt_response.get('name', 'Unknown')}")
            
            variants = prompt_response.get('variants', [])
            if not variants:
                raise ValueError("Prompt has no variants")
            
            variant = variants[0]
            template_type = variant.get('templateType', 'TEXT')
            
            logger.info(f"Template type: {template_type}")
            
            model_id = prompt_response.get('defaultModelId', 'anthropic.claude-3-5-sonnet-20240620-v1:0')
            
            prompt_variables = {
                "user_query": user_query,
                **variables
            }
            
            # Bedrock Runtime
            bedrock_runtime = BedrockClients.get_runtime()
            
            # TEXT 템플릿 처리
            if template_type == 'TEXT':
                template_config = variant.get('templateConfiguration', {})
                template_text = template_config.get('text', {}).get('text', '')
                
                # 변수 치환
                formatted_prompt = template_text
                for var_name, var_value in prompt_variables.items():
                    formatted_prompt = formatted_prompt.replace(f"{{{{{var_name}}}}}", str(var_value))
                
                logger.info(f"Formatted prompt (first 100 chars): {formatted_prompt[:100]}...")
                
                inference_config = variant.get('inferenceConfiguration', {})
                
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": inference_config.get('maxTokens', 4096),
                    "temperature": inference_config.get('temperature', 1.0),
                    "messages": [
                        {
                            "role": "user",
                            "content": formatted_prompt
                        }
                    ]
                }
                
                if 'stopSequences' in inference_config:
                    body['stop_sequences'] = inference_config['stopSequences']
                
                logger.info(f"Invoking model: {model_id}")
                
                response = bedrock_runtime.invoke_model_with_response_stream(
                    modelId=model_id,
                    body=json.dumps(body)
                )
                
                return StreamingHttpResponse(
                    stream_text_prompt_response(response),
                    content_type='text/event-stream'
                )
            
            # CHAT 템플릿 처리
            elif template_type == 'CHAT':
                template_config = variant.get('templateConfiguration', {})
                chat_config = template_config.get('chat', {})
                messages = chat_config.get('messages', [])
                system_prompts = chat_config.get('system', [])
                
                logger.info(f"CHAT template - Messages: {len(messages)}, System prompts: {len(system_prompts)}")
                
                inference_config = variant.get('inferenceConfiguration', {})
                
                formatted_messages = []
                for msg in messages:
                    role = msg.get('role', 'user')
                    content_blocks = msg.get('content', [])
                    
                    formatted_content = []
                    for block in content_blocks:
                        if 'text' in block:
                            text = block['text']
                            for var_name, var_value in prompt_variables.items():
                                text = text.replace(f"{{{{{var_name}}}}}", str(var_value))
                            if text.strip():
                                formatted_content.append({"type": "text", "text": text})
                    
                    if formatted_content:
                        content_text = " ".join([c['text'] for c in formatted_content if 'text' in c])
                        if content_text.strip():
                            formatted_messages.append({
                                "role": role,
                                "content": content_text
                            })
                
                # user 메시지가 없거나 마지막이 user가 아니면 추가
                if not formatted_messages or formatted_messages[-1].get('role') != 'user':
                    formatted_messages.append({
                        "role": "user",
                        "content": user_query
                    })
                elif formatted_messages and not formatted_messages[0].get('content', '').strip():
                    formatted_messages[0]['content'] = user_query
                
                logger.info(f"Formatted {len(formatted_messages)} messages")
                
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": inference_config.get('maxTokens', 4096),
                    "temperature": inference_config.get('temperature', 1.0),
                    "messages": formatted_messages
                }
                
                # System prompt 처리
                if system_prompts:
                    system_text = []
                    for sys_prompt in system_prompts:
                        if 'text' in sys_prompt:
                            text = sys_prompt['text']
                            for var_name, var_value in prompt_variables.items():
                                text = text.replace(f"{{{{{var_name}}}}}", str(var_value))
                            system_text.append(text)
                    
                    if system_text:
                        body['system'] = " ".join(system_text)
                
                if 'stopSequences' in inference_config:
                    body['stop_sequences'] = inference_config['stopSequences']
                
                logger.info(f"Invoking model: {model_id}")
                
                response = bedrock_runtime.invoke_model_with_response_stream(
                    modelId=model_id,
                    body=json.dumps(body)
                )
                
                return StreamingHttpResponse(
                    stream_chat_prompt_response(response),
                    content_type='text/event-stream'
                )
            
            else:
                raise ValueError(f"Unsupported template type: {template_type}")
        
        except bedrock_agent.exceptions.ResourceNotFoundException:
            error_msg = f"Prompt not found: {prompt_id}"
            logger.error(error_msg)
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': error_msg})],
                content_type='text/event-stream'
            )
        
    except Exception as e:
        logger.error(f"Prompt error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return StreamingHttpResponse(
            [sse_event({'type': 'error', 'message': str(e)})],
            content_type='text/event-stream'
        )

def stream_text_prompt_response(response):
    """TEXT 템플릿 스트리밍 응답"""
    full_text = ""
    
    try:
        for event in response['body']:
            chunk = json.loads(event['chunk']['bytes'])
            
            if chunk['type'] == 'content_block_delta':
                text = chunk['delta'].get('text', '')
                if text:
                    full_text += text
                    yield sse_event({'type': 'content', 'text': text})
                    logger.info(f"Sent text chunk: {text[:30]}...")
            
            elif chunk['type'] == 'message_stop':
                logger.info(f"Message stop received")
        
        logger.info(f"Stream complete. Total text length: {len(full_text)}")
        yield sse_event({'type': 'done', 'total_length': len(full_text)})
        
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield sse_event({'type': 'error', 'message': str(e)})

def stream_chat_prompt_response(response):
    """CHAT 템플릿 스트리밍 응답 (버퍼링)"""
    full_text = ""
    buffer = ""
    buffer_size = 10
    
    try:
        for event in response['body']:
            chunk = json.loads(event['chunk']['bytes'])
            
            if chunk['type'] == 'content_block_delta':
                text = chunk['delta'].get('text', '')
                if text:
                    full_text += text
                    buffer += text
                    if len(buffer) >= buffer_size:
                        yield sse_event({'type': 'content', 'text': buffer})
                        logger.info(f"Sent text chunk: {buffer[:30]}...")
                        buffer = ""
            
            elif chunk['type'] == 'message_stop':
                logger.info(f"Message stop received")
        
        # 남은 버퍼 전송
        if buffer:
            yield sse_event({'type': 'content', 'text': buffer})
            logger.info(f"Sent final buffer: {buffer[:30]}...")
        
        logger.info(f"Stream complete. Total text length: {len(full_text)}")
        yield sse_event({'type': 'done', 'total_length': len(full_text)})
        
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield sse_event({'type': 'error', 'message': str(e)})
        
        
# TTS
class TTSSerializer(serializers.Serializer):
    text = serializers.CharField(help_text="음성으로 변환할 텍스트를 입력하세요.")     
    
      
@extend_schema(
    summary="TTS 음성 생성",
    request=TTSSerializer,
    description="텍스트를 입력받아 MP3 음성 파일을 반환합니다.",
    responses={200: OpenApiTypes.BINARY},
    parameters=[]
)   
@csrf_exempt
@api_view(["POST"]) # 보통 긴 텍스트가 올 수 있으므로 POST를 추천합니다
def tts_view(request, promptId=None):
    """텍스트를 음성으로 변환하여 반환"""
    try:
        # data = json.loads(request.body)
        text = request.data.get('text', '')
        
        if not text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        # 1. TTS 파일 생성 (tools/tts.py의 함수 호출)
        # 파일명을 유니크하게 만들기 위해 임시로 'speech.mp3' 사용
        file_path = generate_tts_file(text)
        
        # 2. 파일 응답 전송
        # 전송 후 파일을 삭제하고 싶다면 별도의 처리가 필요하지만, 
        # 우선은 작동 확인을 위해 바로 보냅니다.
        response = FileResponse(open(file_path, 'rb'), content_type='audio/mpeg')
        response['Content-Disposition'] = 'attachment; filename="tts_sample.mp3"'
        return response

    except Exception as e:
        logger.error(f"TTS error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)