import json
import logging
import os
import boto3
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from common.bedrock.clients import BedrockClients
from common.bedrock.streaming import sse_event

from .redis_repository import load_debate_messages

logger = logging.getLogger(__name__)

def parse_json_body(request):
    raw = request.body or b"{}"

    try:
        return json.loads(raw)
    except UnicodeDecodeError:
        pass

    for enc in ("cp949", "euc-kr"):
        try:
            return json.loads(raw.decode(enc))
        except UnicodeDecodeError:
            continue

    raise

def build_debate_messages_json_lines(messages):
    # - type == "CHAT" 만 포함
    # - content가 "__MODE_CHANGE__"로 시작하거나 빈 문자열이면 제외
    # - Bedrock 프롬프트에 넣기 좋은 JSON Lines 문자열로 변환
    lines = []
    used_count = 0

    for m in messages:
        if m.get("type") != "CHAT":
            continue

        content = (m.get("content") or "").strip()
        if not content:
            continue
        if content.startswith("__MODE_CHANGE__"):
            continue

        trimmed = {
            "id": m.get("id"),
            "parentId": m.get("parentId"),
            "sender": m.get("sender"),
            "status": m.get("status"),
            "content": content,
            "createdAt": m.get("createdAt"),
        }
        lines.append(json.dumps(trimmed, ensure_ascii=False))
        used_count += 1

    return "\n".join(lines), used_count

@csrf_exempt
@require_http_methods(["POST"])
def debate_summary(request, room_id: str):
    try:
        # data = json.loads(request.body or "{}")
        data = parse_json_body(request)
        topic = (data.get("topic") or "").strip()
        if not topic:
            return JsonResponse({"error": "Missing topic"}, status=400, json_dumps_params={"ensure_ascii": False})

        # Redis에서 토론 메시지 읽기
        messages = load_debate_messages(room_id)
        if not messages:
            return StreamingHttpResponse(
                [sse_event({"type": "error", "message": "No debate messages in Redis"})],
                content_type="text/event-stream"
            )

        debate_messages_str, used_count = build_debate_messages_json_lines(messages)
        if used_count == 0:
            return StreamingHttpResponse(
                [sse_event({"type": "error", "message": "No usable CHAT messages (all filtered)"})],
                content_type="text/event-stream"
            )

        # Bedrock Prompt ARN
        prompt_arn = os.getenv("AWS_BEDROCK_DEBATE_SUMMARY_PROMPT_ARN")
        if not prompt_arn:
            return StreamingHttpResponse(
                [sse_event({"type": "error", "message": "AWS_BEDROCK_DEBATE_SUMMARY_PROMPT_ARN not configured"})],
                content_type="text/event-stream"
            )

        # Bedrock 프롬프트에 들어갈 변수
        prompt_variables = {
            "topic": topic,
            "debate_messages": debate_messages_str,
        }

        logger.info(f"[DebateSummary] room={room_id} topic={topic} used_count={used_count}")
        text = invoke_bedrock_prompt(prompt_arn, prompt_variables)

        try:
            parsed = json.loads(text)
            return JsonResponse(
                {
                    "room_id": room_id,
                    "topic": topic,
                    "used_message_count": used_count,
                    "result": parsed,
                },
                json_dumps_params={"ensure_ascii": False},
                status=200,
            )
        except Exception:
            return JsonResponse(
                {
                    "room_id": room_id,
                    "topic": topic,
                    "used_message_count": used_count,
                    "text": text,
                },
                json_dumps_params={"ensure_ascii": False},
                status=200,
            )

    except Exception as e:
        logger.error(f"Debate summary error: {str(e)}", exc_info=True)
        return JsonResponse(
            {"error": str(e)},
            status=500,
            json_dumps_params={"ensure_ascii": False},
        )

@csrf_exempt
@require_http_methods(["POST"])
def recommend_debate_topics(request):
    """토픽 추천 전용 엔드포인트 - JSON 응답"""
    try:
        data = json.loads(request.body)
        
        user_query = data.get('user_query')
        
        if not user_query:
            return JsonResponse({'error': 'Missing user_query'}, status=400)
        
        # 환경변수에서 Prompt ARN 가져오기
        prompt_arn = os.getenv('AWS_BEDROCK_DEBATE_TOPICS_PROMPT_ARN')
        
        if not prompt_arn:
            return JsonResponse({'error': 'AWS_BEDROCK_DEBATE_TOPICS_PROMPT_ARN not configured'}, status=500)
        
        logger.info(f"Debate topics request - Query: {user_query[:50]}...")
        logger.info(f"Using Prompt ARN: {prompt_arn}")
        
        bedrock_agent = boto3.client(
            service_name='bedrock-agent',
            region_name=os.getenv('AWS_REGION', 'ap-northeast-2')
        )
        
        # Prompt 정보 가져오기
        prompt_response = bedrock_agent.get_prompt(
            promptIdentifier=prompt_arn
        )
        
        logger.info(f"Prompt retrieved: {prompt_response.get('name', 'Unknown')}")
        
        variants = prompt_response.get('variants', [])
        if not variants:
            raise ValueError("Prompt has no variants")
        
        variant = variants[0]
        template_type = variant.get('templateType', 'TEXT')
        model_id = prompt_response.get('defaultModelId', 'anthropic.claude-3-5-sonnet-20240620-v1:0')
        
        prompt_variables = {"user_query": user_query}
        
        bedrock_runtime = BedrockClients.get_runtime()
        
        body = {}
        
        # TEXT 템플릿 처리
        if template_type == 'TEXT':
            template_config = variant.get('templateConfiguration', {})
            template_text = template_config.get('text', {}).get('text', '')
            
            formatted_prompt = template_text
            for var_name, var_value in prompt_variables.items():
                formatted_prompt = formatted_prompt.replace(f"{{{{{var_name}}}}}", str(var_value))
            
            inference_config = variant.get('inferenceConfiguration', {})
            
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": inference_config.get('maxTokens', 4096),
                "temperature": inference_config.get('temperature', 1.0),
                "messages": [{"role": "user", "content": formatted_prompt}]
            }
            
            if 'stopSequences' in inference_config:
                body['stop_sequences'] = inference_config['stopSequences']
            
            # 동기 호출로 전체 응답 받기
            response = bedrock_runtime.invoke_model(
                modelId=model_id,
                body=json.dumps(body)
            )
            
            result = json.loads(response['body'].read())
            full_text = result['content'][0]['text']
            
            return parse_and_return_topics(full_text)
        
        # ✅ CHAT 템플릿 처리 추가
        elif template_type == 'CHAT':
            template_config = variant.get('templateConfiguration', {})
            chat_config = template_config.get('chat', {})
            messages = chat_config.get('messages', [])
            system_prompts = chat_config.get('system', [])
            
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
                        # 변수 치환
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
            
            response = bedrock_runtime.invoke_model(
                modelId=model_id,
                body=json.dumps(body)
            )
            
            result = json.loads(response['body'].read())
            full_text = result['content'][0]['text']
            
            return parse_and_return_topics(full_text)
        
        else:
            raise ValueError(f"Unsupported template type: {template_type}")
            
        logger.info(f"Invoking model: {model_id}")
        
        # Invoke Model (Non-Streaming)
        response = bedrock_runtime.invoke_model(
            modelId=model_id,
            body=json.dumps(body)
        )
        
        response_body = json.loads(response.get('body').read())
        
        # Extract text content
        final_text = ""
        for content in response_body.get('content', []):
            if content.get('type') == 'text':
                final_text += content.get('text', '')
                
        logger.info(f"Model response received: {len(final_text)} chars")
        
        # Parse JSON from model response
        # 모델이 JSON 블록(```json ... ```)으로 감싸서 줄 수도 있으므로 처리
        clean_text = final_text.strip()
        if clean_text.startswith('```json'):
            clean_text = clean_text[7:]
        if clean_text.endswith('```'):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
            
        try:
            result_json = json.loads(clean_text)
            return JsonResponse(result_json, safe=False)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse model output as JSON: {clean_text[:100]}...")
            # Fallback: Just return text wrapped in structure if needed, or error
            # But frontend expects debate_topics structure. 
            # If parsing fails, it's likely the model didn't follow instructions.
            return JsonResponse({
                'type': 'error',
                'message': 'Failed to parse AI response',
                'raw_response': final_text
            }, status=500)
        
    except Exception as e:
        logger.error(f"Debate topics error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({'error': str(e)}, status=500)


def parse_and_return_topics(full_text: str):
    """
    LLM 응답 텍스트에서 토픽을 파싱하여 JSON 반환
    """
    import re
    
    try:
        # JSON 블록 추출 시도
        json_match = re.search(r'\[.*\]', full_text, re.DOTALL)
        if json_match:
            topics_data = json.loads(json_match.group())
            return JsonResponse({'debate_topics': topics_data})
        
        # JSON 없으면 텍스트 파싱
        topics = []
        lines = full_text.strip().split('\n')
        current_topic = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 번호로 시작하는 라인 (1. 토픽명)
            if re.match(r'^\d+\.\s*', line):
                if current_topic:
                    topics.append(current_topic)
                topic_text = re.sub(r'^\d+\.\s*', '', line)
                current_topic = {'topic': topic_text, 'description': ''}
            elif current_topic:
                current_topic['description'] += ' ' + line
        
        if current_topic:
            topics.append(current_topic)
        
        # Clean up descriptions
        for topic in topics:
            topic['description'] = topic['description'].strip()
        
        return JsonResponse({'debate_topics': topics})
        
    except Exception as e:
        logger.error(f"Parse error: {str(e)}")
        # 파싱 실패 시 원본 텍스트 반환
        return JsonResponse({
            'debate_topics': [{
                'topic': '토픽 생성됨',
                'description': full_text[:500]
            }]
        })

def stream_debate_response(response):
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
            
            elif chunk['type'] == 'message_stop':
                logger.info(f"Message stop received")
        
        logger.info(f"Stream complete. Total text length: {len(full_text)}")
        yield sse_event({'type': 'done', 'total_length': len(full_text)})
        
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}")
        yield sse_event({'type': 'error', 'message': str(e)})

def stream_debate_response_buffered(response):
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

def invoke_bedrock_prompt(prompt_arn: str, prompt_variables: dict) -> str:
    
    bedrock_agent = boto3.client(
        service_name="bedrock-agent",
        region_name=os.getenv("AWS_REGION", "ap-northeast-2")
    )
    bedrock_runtime = BedrockClients.get_runtime()

    prompt_response = bedrock_agent.get_prompt(promptIdentifier=prompt_arn)
    logger.info(f"Prompt retrieved: {prompt_response.get('name', 'Unknown')}")

    variants = prompt_response.get("variants", [])
    if not variants:
        raise ValueError("Prompt has no variants")

    variant = variants[0]
    template_type = variant.get("templateType", "TEXT")
    model_id = prompt_response.get("defaultModelId", "anthropic.claude-3-5-sonnet-20240620-v1:0")
    inference_config = variant.get("inferenceConfiguration", {})

    if template_type == "TEXT":
        template_text = variant.get("templateConfiguration", {}).get("text", {}).get("text", "")
        formatted_prompt = template_text
        for var_name, var_value in prompt_variables.items():
            formatted_prompt = formatted_prompt.replace(f"{{{{{var_name}}}}}", str(var_value))

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": inference_config.get("maxTokens", 4096),
            "temperature": inference_config.get("temperature", 1.0),
            "messages": [{"role": "user", "content": formatted_prompt}],
        }
        if "stopSequences" in inference_config:
            body["stop_sequences"] = inference_config["stopSequences"]

    elif template_type == "CHAT":
        chat_config = variant.get("templateConfiguration", {}).get("chat", {})
        messages = chat_config.get("messages", [])
        system_prompts = chat_config.get("system", [])

        formatted_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content_blocks = msg.get("content", [])
            text_parts = []

            for block in content_blocks:
                if "text" in block:
                    text = block["text"]
                    for var_name, var_value in prompt_variables.items():
                        text = text.replace(f"{{{{{var_name}}}}}", str(var_value))
                    if text.strip():
                        text_parts.append(text)

            if text_parts:
                formatted_messages.append({"role": role, "content": " ".join(text_parts)})

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": inference_config.get("maxTokens", 4096),
            "temperature": inference_config.get("temperature", 1.0),
            "messages": formatted_messages,
        }

        # system prompt
        if system_prompts:
            system_texts = []
            for sys_prompt in system_prompts:
                if "text" in sys_prompt:
                    text = sys_prompt["text"]
                    for var_name, var_value in prompt_variables.items():
                        text = text.replace(f"{{{{{var_name}}}}}", str(var_value))
                    if text.strip():
                        system_texts.append(text)
            if system_texts:
                body["system"] = " ".join(system_texts)

        if "stopSequences" in inference_config:
            body["stop_sequences"] = inference_config["stopSequences"]

    else:
        raise ValueError(f"Unsupported template type: {template_type}")

    resp = bedrock_runtime.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        accept="application/json",
        contentType="application/json",
    )

    raw = resp["body"].read().decode("utf-8")
    data = json.loads(raw)

    text = ""
    content = data.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            text = first.get("text", "") or ""

    if not text:
        text = data.get("completion", "") or ""

    return text
