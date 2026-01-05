import json
import logging
import os
import boto3
from django.http import StreamingHttpResponse, HttpResponseNotAllowed
from django.views.decorators.csrf import csrf_exempt
from common.bedrock.clients import BedrockClients
from common.bedrock.streaming import sse_event

from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework.decorators import api_view
from rest_framework import serializers
from django.http import JsonResponse, FileResponse
from django.shortcuts import get_object_or_404
from apps.tools.tts import generate_tts_file

logger = logging.getLogger(__name__)

from uuid import UUID
from apps.prompt.redis_chat_repository import RedisChatRepository
from apps.prompt.dto import MessageDTO
from apps.prompt.models import AIPerson


def prompt_view(request, promptId=None):
    """Bedrock Prompt 호출 (스트리밍) - 완전 동기 버전"""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    
    env_prompt_arn = os.getenv('AWS_BEDROCK_AI_PERSON_ARN')
    
    try:
        data = json.loads(request.body)
        
        # body에서 파라미터 받기
        prompt_id = data.get('promptId') or promptId
        user_query = data.get('message') or data.get('user_query')
        user_id = data.get('userId')

        # 필수 파라미터 검증
        if not prompt_id or not user_query:
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': 'Missing prompt_id or message'})],
                content_type='text/event-stream'
            )
        
        if not user_id:
            return StreamingHttpResponse(
                [sse_event({"type": "error", "message": "Missing userId in body"})],
                content_type="text/event-stream",
            )
        
        # UUID 검증
        try:
            user_id = UUID(user_id)
        except ValueError:
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': 'Invalid userId'})],
                content_type='text/event-stream'
            )

        # Redis 설정
        redis_repo = RedisChatRepository()
        history_key = redis_repo.build_aiperson_key(prompt_id, user_id)
        user_msg = MessageDTO.user(user_query)

        # 콜백 함수 생성 (클로저로 변수 캡처)
        def on_done_callback(full_response: str):
            """스트리밍 완료 후 Redis 저장"""
            try:
                assistant_msg = MessageDTO.assistant(full_response)
                redis_repo.append_message(history_key, user_msg)
                redis_repo.append_message(history_key, assistant_msg)
                logger.info(f"Saved chat history key={history_key} (user_len={len(user_query)}, assistant_len={len(full_response)})")
            except Exception as e:
                logger.error(f"Redis save failed: {str(e)}")
        
        # AI Person 정보 가져오기 (동기)
        person_variables = {}
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
        except Exception as e:
            logger.error(f"DB Error: {e}")

        # 변수 준비
        variables = data.get('variables', {})
        prompt_variables = {
            "user_query": user_query,
            **person_variables,
            **variables
        }

        logger.info(f"Prompt variables: {list(prompt_variables.keys())}")

        # Bedrock Agent 클라이언트
        bedrock_agent = boto3.client(
            service_name='bedrock-agent',
            region_name=os.getenv('CLOUD_AWS_REGION', 'ap-northeast-2')
        )
        
        # Prompt ARN 결정
        if prompt_id and prompt_id.startswith('arn:'):
            prompt_identifier = prompt_id
        else:
            prompt_identifier = env_prompt_arn

        if not prompt_identifier:
            logger.error("에러: 환경변수 AWS_BEDROCK_AI_PERSON_ARN을 읽지 못했습니다.")
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': 'Missing prompt ARN configuration'})],
                content_type='text/event-stream'
            )

        logger.info(f"Using Prompt ARN: {prompt_identifier}")
        
        try:
            # Prompt 가져오기 (동기)
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
                
                # Bedrock 호출 (동기)
                response = bedrock_runtime.invoke_model_with_response_stream(
                    modelId=model_id,
                    body=json.dumps(body)
                )
                
                return StreamingHttpResponse(
                    stream_text_prompt_response(response, on_done=on_done_callback),
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
                
                # 메시지 포맷팅
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
                
                # user 메시지 확인 및 추가
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
                
                # Bedrock 호출 (동기)
                response = bedrock_runtime.invoke_model_with_response_stream(
                    modelId=model_id,
                    body=json.dumps(body)
                )
                
                return StreamingHttpResponse(
                    stream_chat_prompt_response(response, on_done=on_done_callback),
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


def stream_chat_prompt_response(response, on_done=None):
    """CHAT 템플릿 스트리밍 응답 (완전 동기)"""
    full_text = ""
    
    stream = response['body']
    
    try:
        # boto3 iterator를 그대로 사용
        for event in stream:
            chunk = json.loads(event['chunk']['bytes'])
            
            if chunk['type'] == 'content_block_delta':
                text = chunk['delta'].get('text', '')
                if text:
                    full_text += text
                    yield sse_event({'type': 'content', 'text': text})
            
            elif chunk['type'] == 'message_stop':
                logger.info(f"Message stop received")
                break
        
        logger.info(f"Stream complete. Total text length: {len(full_text)}")
        
        # 완료 콜백 실행
        if callable(on_done):
            on_done(full_text)
        
        yield sse_event({'type': 'done', 'total_length': len(full_text)})
        
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield sse_event({'type': 'error', 'message': str(e)})


def stream_text_prompt_response(response, on_done=None):
    """TEXT 템플릿 스트리밍 응답 (완전 동기)"""
    full_text = ""
    
    stream = response['body']
    
    try:
        # boto3 iterator를 그대로 사용
        for event in stream:
            chunk = json.loads(event['chunk']['bytes'])
            
            if chunk['type'] == 'content_block_delta':
                text = chunk['delta'].get('text', '')
                if text:
                    full_text += text
                    yield sse_event({'type': 'content', 'text': text})
            
            elif chunk['type'] == 'message_stop':
                logger.info(f"Message stop received")
                break
        
        logger.info(f"Stream complete. Total text length: {len(full_text)}")
        
        # 완료 콜백 실행
        if callable(on_done):
            on_done(full_text)
        
        yield sse_event({'type': 'done', 'total_length': len(full_text)})
        
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield sse_event({'type': 'error', 'message': str(e)})


# TTS (이미 동기이므로 변경 없음)
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
        voice_id = 'Seoyeon'
        
        if prompt_id:
            try:
                person = AIPerson.objects.get(promptId=prompt_id)
                if person.voiceId:
                    voice_id = person.voiceId
                logger.info(f"TTS 생성 시작 - 인물: {person.name}, 목소리: {voice_id}")
            except AIPerson.DoesNotExist:
                logger.warning(f"promptId {prompt_id}를 찾을 수 없어 기본 목소리(Seoyeon)를 사용합니다.")

        # 3. Amazon Polly를 통해 파일 생성
        file_path = generate_tts_file(text, voice_id=voice_id)

        if file_path and os.path.exists(file_path):
            # 4. 파일 스트리밍 응답
            response = FileResponse(open(file_path, 'rb'), content_type='audio/wav')
            response['Content-Disposition'] = f'inline; filename="response_{voice_id}.wav"'
            return response
        else:
            return JsonResponse({'error': '음성 파일 생성 실패'}, status=500)

    except Exception as e:
        logger.error(f"TTS 생성 중 예외 발생: {str(e)}")
        return JsonResponse({'error': 'Internal Server Error'}, status=500)