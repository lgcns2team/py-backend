import json
import logging
import os
import boto3
from django.http import StreamingHttpResponse, HttpResponseNotAllowed
from asgiref.sync import sync_to_async
from common.bedrock.clients import BedrockClients
from common.bedrock.streaming import sse_event

logger = logging.getLogger(__name__)

from uuid import UUID
from apps.prompt.redis_chat_repository import RedisChatRepository
from apps.prompt.dto import MessageDTO
from apps.prompt.models import AIPerson


async def prompt_view(request, promptId=None):
    """Bedrock Prompt 호출 (ASGI 환경용 async view)"""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    
    env_prompt_arn = os.getenv('AWS_BEDROCK_AI_PERSON_ARN')
    
    try:
        data = json.loads(request.body)
        
        prompt_id = data.get('promptId') or promptId
        user_query = data.get('message') or data.get('user_query')
        user_id = data.get('userId')

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

        # Async 콜백
        async def on_done_callback(full_response: str):
            try:
                assistant_msg = MessageDTO.assistant(full_response)
                await sync_to_async(redis_repo.append_message)(history_key, user_msg)
                await sync_to_async(redis_repo.append_message)(history_key, assistant_msg)
                logger.info(f"Saved chat history key={history_key}")
            except Exception as e:
                logger.error(f"Redis save failed: {str(e)}")
        
        # AI Person 정보 가져오기 (async ORM)
        person_variables = {}
        try:
            ai_person = await AIPerson.objects.aget(promptId=prompt_id)
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
        
        if prompt_id and prompt_id.startswith('arn:'):
            prompt_identifier = prompt_id
        else:
            prompt_identifier = env_prompt_arn

        if not prompt_identifier:
            logger.error("에러: 환경변수 AWS_BEDROCK_AI_PERSON_ARN을 읽지 못했습니다.")
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': 'Missing prompt ARN'})],
                content_type='text/event-stream'
            )

        logger.info(f"Using Prompt ARN: {prompt_identifier}")
        
        try:
            # Bedrock 호출은 blocking이므로 sync_to_async로 감싸기
            prompt_response = await sync_to_async(bedrock_agent.get_prompt)(
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
            
            bedrock_runtime = BedrockClients.get_runtime()
            
            # CHAT 템플릿 처리
            if template_type == 'CHAT':
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
                
                # Bedrock 스트리밍 호출 (blocking이므로 sync_to_async로 감싸기)
                response = await sync_to_async(bedrock_runtime.invoke_model_with_response_stream)(
                    modelId=model_id,
                    body=json.dumps(body)
                )
                
                return StreamingHttpResponse(
                    stream_chat_prompt_response_async(response, on_done=on_done_callback),
                    content_type='text/event-stream'
                )
            
            # TEXT 템플릿 처리 (동일한 패턴)
            elif template_type == 'TEXT':
                # ... (TEXT 처리 로직, CHAT과 유사)
                pass
            
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


async def stream_chat_prompt_response_async(response, on_done=None):
    """ASGI 환경용 async generator - boto3 blocking을 thread pool에서 처리"""
    full_text = ""
    stream = response['body']
    
    try:
        # boto3 iterator는 blocking이므로 thread pool에서 실행
        async for chunk_data in _iterate_stream_async(stream):
            if chunk_data['type'] == 'content_block_delta':
                text = chunk_data['delta'].get('text', '')
                if text:
                    full_text += text
                    yield sse_event({'type': 'content', 'text': text})
            
            elif chunk_data['type'] == 'message_stop':
                logger.info("Message stop received")
                break
        
        logger.info(f"Stream complete. Total text length: {len(full_text)}")
        
        if callable(on_done):
            await on_done(full_text)
        
        yield sse_event({'type': 'done', 'total_length': len(full_text)})
        
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield sse_event({'type': 'error', 'message': str(e)})


async def _iterate_stream_async(stream):
    """boto3 blocking iterator를 async generator로 변환"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    executor = ThreadPoolExecutor(max_workers=1)
    loop = asyncio.get_event_loop()
    
    def get_next_chunk():
        """Thread pool에서 실행될 blocking 함수"""
        try:
            event = next(iter(stream))
            return json.loads(event['chunk']['bytes'])
        except StopIteration:
            return None
    
    while True:
        # blocking iterator를 별도 스레드에서 실행
        chunk = await loop.run_in_executor(executor, get_next_chunk)
        
        if chunk is None:
            break
        
        yield chunk