import json
import logging
import os
import boto3
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from common.bedrock.clients import BedrockClients
from common.bedrock.streaming import sse_event

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["POST"])
def recommend_debate_topics(request):
    """토픽 추천 전용 엔드포인트"""
    try:
        data = json.loads(request.body)
        
        user_query = data.get('user_query')
        
        if not user_query:
            return JsonResponse({
                'type': 'error',
                'message': 'Missing user_query'
            }, status=400)
        
        # 환경변수에서 Prompt ARN 가져오기
        prompt_arn = os.getenv('AWS_BEDROCK_DEBATE_TOPICS_PROMPT_ARN')
        
        if not prompt_arn:
            return JsonResponse({
                'type': 'error',
                'message': 'AWS_BEDROCK_DEBATE_TOPICS_PROMPT_ARN not configured'
            }, status=500)
        
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
            
        # CHAT 템플릿 처리
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
        return JsonResponse({
            'type': 'error',
            'message': str(e)
        }, status=500)