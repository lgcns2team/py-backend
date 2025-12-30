import json
import logging
import os
import boto3
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from common.bedrock.clients import BedrockClients
from common.bedrock.streaming import sse_event

from uuid import UUID
from apps.prompt.redis_chat_repository import RedisChatRepository
from apps.prompt.dto import MessageDTO

import tempfile
from apps.stt.services.s3_service import S3Service
from apps.stt.services.whisper_service import transcribe_audio

logger = logging.getLogger(__name__)

from apps.prompt.models import AIPerson

@csrf_exempt
@require_http_methods(["POST"])
def prompt_view(request, promptId=None):
    """Bedrock Prompt 호출 (스트리밍) - FastAPI 로직 포팅"""
    env_prompt_arn = os.getenv('AWS_BEDROCK_AI_PERSON')

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
        
        # ✅ FastAPI와 동일한 로직: ARN 구성 (버전 없음!)
        if prompt_id.startswith('arn:'):
            prompt_identifier = prompt_id
        else:
            prompt_identifier = env_prompt_arn
        
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