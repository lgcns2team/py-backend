import json
import logging
import os
import boto3
import requests
from uuid import UUID
from contextlib import closing

from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

# Bedrock 관련 공통 모듈
from common.bedrock.clients import BedrockClients
from common.bedrock.streaming import sse_event

# API 문서화 및 REST 프레임워크 관련
from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework.decorators import api_view
from rest_framework import serializers

# 모델 및 레포지토리
from apps.prompt.models import AIPerson
from apps.prompt.redis_chat_repository import RedisChatRepository
from apps.prompt.dto import MessageDTO

logger = logging.getLogger(__name__)

from apps.prompt.models import AIPerson

from dotenv import load_dotenv
load_dotenv()

@csrf_exempt
@require_http_methods(["POST"])
def prompt_view(request, promptId=None):
    """Bedrock Prompt 호출 (스트리밍) - FastAPI 로직 포팅"""
    env_prompt_arn = os.getenv('AWS_BEDROCK_AI_PERSON_ARN')
    
    try:
        data = json.loads(request.body)
        
        # promptId는 URL에서, user_query는 body에서
        prompt_id = promptId or data.get('prompt_id')
        user_query = data.get('message') or data.get('user_query')
        
        user_id = request.GET.get("userId") or data.get("userId")

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
            logger.error("에러: 환경변수 AWS_BEDROCK_AI_PERSON을 읽지 못했습니다.")

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
    summary="AI 답변 TTS 변환(Typecast 사용)",
    request=TTSSerializer,
    description="Typecast API를 사용하여 답변 텍스트를 고품질 음성으로 변환합니다.",
    responses={200: OpenApiTypes.BINARY},
) 
@csrf_exempt
@api_view(["POST"]) 
def tts_view(request):
    """Bedrock의 최종 응답을 음성으로 변환"""
    try:
        logger.info("=" * 50)
        logger.info("🎤 TTS 요청 시작")
        logger.info("=" * 50)
        
        # 1. 요청 데이터 파싱 
        logger.info("📝 Step 1: 요청 데이터 파싱 중...")
        text = request.data.get('text', '')
        prompt_id = request.data.get('promptId')
        
        logger.info(f"   - text 길이: {len(text)} 문자")
        logger.info(f"   - text 미리보기: {text[:100]}..." if len(text) > 100 else f"   - text: {text}")
        logger.info(f"   - promptId: {prompt_id}")
        
        if not text:
            logger.error("❌ 텍스트가 제공되지 않음")
            return JsonResponse({'error': 'No text provided'}, status=400)

        # 2. 인물 정보 조회
        logger.info("👤 Step 2: 인물 정보 조회 중...")
        voice_id = None  # 기본값 설정
        
        if prompt_id:
            try:
                person = AIPerson.objects.get(promptId=prompt_id)
                logger.info(f"   ✅ 인물 찾음: {person.name}")
                
                if person.voiceId:
                    voice_id = person.voiceId
                    logger.info(f"   ✅ 목소리 ID: {voice_id}")
                else:
                    logger.warning(f"   ⚠️  인물 {person.name}에 voiceId가 없음")
                    
            except AIPerson.DoesNotExist:
                logger.warning(f"   ⚠️  promptId {prompt_id}를 찾을 수 없습니다.")
        else:
            logger.warning("   ⚠️  promptId가 제공되지 않음")

        if not voice_id:
            logger.error("❌ voice_id를 확인할 수 없습니다.")
            return JsonResponse({'error': 'voice_id not found'}, status=400)

        # 3. Typecast API 준비
        logger.info("🔧 Step 3: Typecast API 준비 중...")
        typecast_api_key = os.getenv('TYPECAST_API_KEY')
        
        if not typecast_api_key:
            logger.error("❌ TYPECAST_API_KEY 환경 변수가 설정되지 않음")
            return JsonResponse({'error': 'TYPECAST_API_KEY not configured'}, status=500)
        
        logger.info(f"   ✅ API 키 확인됨: {typecast_api_key[:10]}...")
        
        url = "https://api.typecast.ai/v1/text-to-speech"
        logger.info(f"   - API URL: {url}")
        
        headers = {
            "X-API-KEY": typecast_api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text,
            "voice_id": voice_id,
            "language": "ko",
            "model": "ssfm-v21",
            "output": {
                "audio_format": "mp3"
            },
            "options": {
                "pitch": -2
            }
        }
        
        logger.info("   - Payload 생성 완료:")
        logger.info(f"     * voice_id: {payload['voice_id']}")
        logger.info(f"     * language: {payload['language']}")
        logger.info(f"     * model: {payload['model']}")
        logger.info(f"     * audio_format: {payload['output']['audio_format']}")
        logger.info(f"     * pitch: {payload['options']['pitch']}")

        # 4. Typecast API 호출
        logger.info("🌐 Step 4: Typecast API 호출 중...")
        logger.info(f"   - 타임아웃: 60초")
        
        try:
            response = requests.post(
                url, 
                json=payload, 
                headers=headers, 
                stream=True, 
                timeout=60
            )
            
            logger.info(f"   ✅ API 응답 수신: HTTP {response.status_code}")
            logger.info(f"   - Response Headers: {dict(response.headers)}")
            
        except requests.exceptions.Timeout:
            logger.error("❌ API 호출 타임아웃 (60초 초과)")
            return JsonResponse({'error': 'Typecast API timeout'}, status=504)
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ API 연결 실패: {str(e)}")
            return JsonResponse({'error': 'Cannot connect to Typecast API'}, status=503)
        except Exception as e:
            logger.error(f"❌ API 호출 중 예외 발생: {str(e)}")
            return JsonResponse({'error': f'API request failed: {str(e)}'}, status=500)
        
        # 5. 응답 처리
        logger.info("📦 Step 5: 응답 처리 중...")
        
        if response.status_code == 200:
            logger.info("   ✅ 음성 생성 성공!")
            
            # Content-Length 확인
            content_length = response.headers.get('Content-Length')
            if content_length:
                logger.info(f"   - 오디오 파일 크기: {int(content_length) / 1024:.2f} KB")
            
            res = StreamingHttpResponse(
                response.iter_content(chunk_size=8192), 
                content_type='audio/mpeg'
            )
            res['Content-Disposition'] = f'inline; filename="response_{voice_id}.mp3"'
            
            logger.info(f"   - 파일명: response_{voice_id}.mp3")
            logger.info("=" * 50)
            logger.info("✅ TTS 요청 완료 - 스트리밍 시작")
            logger.info("=" * 50)
            
            return res
            
        else:
            logger.error(f"❌ API 응답 에러: HTTP {response.status_code}")
            
            # 에러 응답 본문 확인
            try:
                error_body = response.json()
                logger.error(f"   - 에러 내용: {error_body}")
            except:
                error_text = response.text[:500]
                logger.error(f"   - 에러 텍스트: {error_text}")
            
            return JsonResponse({
                'error': '오디오 파일 생성 실패',
                'status_code': response.status_code,
                'detail': response.text[:200]
            }, status=500)

    except Exception as e:
        logger.error("=" * 50)
        logger.error(f"❌ TTS 생성 중 예외 발생")
        logger.error(f"   - 에러 타입: {type(e).__name__}")
        logger.error(f"   - 에러 메시지: {str(e)}")
        logger.error("=" * 50)
        
        import traceback
        logger.error(f"스택 트레이스:\n{traceback.format_exc()}")
        
        return JsonResponse({
            'error': str(e),
            'error_type': type(e).__name__
        }, status=500)