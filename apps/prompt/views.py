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
from django.shortcuts import get_object_or_404
from apps.tools.tts import generate_tts_file
logger = logging.getLogger(__name__)

# from apps.prompt.redis_repo import RedisChatRepository, MessageDTO
from uuid import UUID
from apps.prompt.redis_chat_repository import RedisChatRepository
from apps.prompt.dto import MessageDTO

logger = logging.getLogger(__name__)

from apps.prompt.models import AIPerson

@csrf_exempt
@require_http_methods(["POST"])
def prompt_view(request, promptId=None):
    """Bedrock Prompt 호출 (스트리밍) - FastAPI 로직 포팅"""
    env_prompt_arn = os.getenv('BEDROCK_AI_PERSON')
    
    try:
        data = json.loads(request.body)
        
        # promptId는 URL에서, user_query는 body에서
        prompt_id = promptId or data.get('prompt_id')
        user_query = data.get('message') or data.get('user_query')
        
        user_id = request.GET.get("userId")

        if not prompt_id or not user_query:
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': 'Missing prompt_id or message'})],
                content_type='text/event-stream'
            )
        
        if not user_id:
            return StreamingHttpResponse(
                [sse_event({"type": "error", "message": "Missing userId in query param"})],
                content_type="text/event-stream",
            )
        
        try:
            user_id = UUID(user_id)
        except ValueError:
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': 'Invalid userId'})],
                content_type='text/event-stream'
            )

        redis_repo = RedisChatRepository()
        history_key = redis_repo.build_aiperson_key(prompt_id, user_id)

        user_msg = MessageDTO.user(user_query)

        def on_done_save(full_response: str):
            try:
                assistant_msg = MessageDTO.assistant(full_response)
                redis_repo.append_message(history_key, user_msg)
                redis_repo.append_message(history_key, assistant_msg)
                logger.info("Saved chat history key=%s (user_len=%s, assistant_len=%s)",
                            history_key, len(user_query), len(full_response))
            except Exception as e:
                logger.error("Redis save failed: %s", str(e))
    
        try:
            ai_person = AIPerson.objects.get(promptId=prompt_id)
            logger.info(f"Found AI Person: {ai_person.name} from {ai_person.era}")

            person_variables = {
                'name': ai_person.name,
                'era': ai_person.era,
                'summary': ai_person.summary or '',
                'year': str(ai_person.year) if ai_person.year else '',
                'greeting_message': ai_person.greetingMessage or '',
                'ex_question': ai_person.exQuestion or '',
            }

            if ai_person.latitude is not None and ai_person.longitude is not None:
                person_variables['location'] = f"위도: {ai_person.latitude}, 경도: {ai_person.longitude}"

        except AIPerson.DoesNotExist:
            logger.warning(f"AI Person not found for prompt_id: {prompt_id}")
            person_variables = {}

        variables = data.get('variables', {})
        prompt_variables = {
            "user_query": user_query,
            **person_variables,  # AI 인물 정보
            **variables
        }

        logger.info(f"Prompt variables: {list(prompt_variables.keys())}")

        # Bedrock Agent 클라이언트
        bedrock_agent = boto3.client(
            service_name='bedrock-agent',
            region_name=os.getenv('CLOUD_AWS_REGION', 'ap-northeast-2')
        )
        
        if prompt_id and prompt_id.startswith('arn:'):
            prompt_identifier = prompt_id
        else:
            prompt_identifier = env_prompt_arn

        if not prompt_identifier:
            logger.error("에러: 환경변수 BEDROCK_AI_PERSON을 읽지 못했습니다.")

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
                    stream_text_prompt_response(response, on_done=on_done_save),
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
                    stream_chat_prompt_response(response, on_done=on_done_save),
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

def stream_text_prompt_response(response, on_done=None):
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
        
        if callable(on_done):
            on_done(full_text)
        
        yield sse_event({'type': 'done', 'total_length': len(full_text)})
        
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield sse_event({'type': 'error', 'message': str(e)})

def stream_chat_prompt_response(response, on_done=None):
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
        
        if callable(on_done):
            on_done(full_text)
        
        yield sse_event({'type': 'done', 'total_length': len(full_text)})
        
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield sse_event({'type': 'error', 'message': str(e)})
        
        
# TTS
class TTSSerializer(serializers.Serializer):
    text = serializers.CharField(help_text="bedrock이 생성한 전체 답변 텍스트")     
    promptId = serializers.CharField(help_text="인물의 고유 ID (목소리 매핑용)")
      
@extend_schema(
    summary="AI 답변 TTS 변환",
    request=TTSSerializer,
    description="Bedrock이 생성한 답변 텍스트를 해당 인물의 목소리로 변환합니다.",
    responses={200: OpenApiTypes.BINARY},
)   
@csrf_exempt
@api_view(["POST"]) 
def tts_view(request):
    """Bedrock의 최종 응답을 음성으로 변환"""
    try:
        # 1. 요청 데이터 파싱 
        text = request.data.get('text', '')
        prompt_id = request.data.get('promptId')
        
        if not text:
            return JsonResponse({'error': 'No text provided'}, status=400)

        # 2. DB에서 인물의 목소리 ID 찾기
        # 기본값은 'Seoyeon'(여성)으로 설정 (역사 인물 특성)
        voice_id = 'Seoyeon'
        
        if prompt_id:
            try:
                # DB 조회
                person = AIPerson.objects.get(promptId=prompt_id)
                if person.voiceId:
                    voice_id = person.voiceId
                logger.info(f"TTS 생성 시작 - 인물: {person.name}, 목소리: 카리나")
            except AIPerson.DoesNotExist:
                logger.warning(f"promptId {prompt_id}를 찾을 수 없어 기본 목소리(Seoyeon)를 사용합니다.")

        # 3. Amazon Polly를 통해 파일 생성
        # 이전에 바꾼 tts.py의 generate_tts_file(text, voice_id) 호출
        file_path = generate_tts_file(text, voice_id=voice_id)

        if file_path and os.path.exists(file_path):
            # 4. 파일 스트리밍 응답 (전송 후 브라우저에서 바로 재생 가능)
            response = FileResponse(open(file_path, 'rb'), content_type='audio/wav')
            # 파일명에 voice_id를 포함시켜 어떤 목소리인지 알기 쉽게 함
            response['Content-Disposition'] = f'inline; filename="response_{voice_id}.wav"'
            return response
        else:
            return JsonResponse({'error': '음성 파일 생성 실패'}, status=500)

    except Exception as e:
        logger.error(f"TTS 생성 중 예외 발생: {str(e)}")
        return JsonResponse({'error': 'Internal Server Error'}, status=500)