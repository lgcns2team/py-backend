import json
import logging
import os
import boto3
from django.http import StreamingHttpResponse
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
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': 'Missing user_query'})],
                content_type='text/event-stream'
            )
        
        # ✅ 환경변수에서 Prompt ID 가져오기
        prompt_arn = os.getenv('AWS_BEDROCK_DEBATE_TOPICS_PROMPT_ARN')
        
        if not prompt_arn:
            return StreamingHttpResponse(
                [sse_event({'type': 'error', 'message': 'AWS_BEDROCK_DEBATE_TOPICS_PROMPT_ARN not configured'})],
                content_type='text/event-stream'
            )
        
        logger.info(f"Debate topics request - Query: {user_query[:50]}...")
        logger.info(f"Using Prompt ARN: {prompt_arn}")
        
        # Bedrock Agent 클라이언트
        bedrock_agent = boto3.client(
            service_name='bedrock-agent',
            region_name=os.getenv('CLOUD_AWS_REGION', 'ap-northeast-2')
        )
        
        # Prompt 가져오기
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
        
        prompt_variables = {
            "user_query": user_query
        }
        
        bedrock_runtime = BedrockClients.get_runtime()
        
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
                "messages": [
                    {
                        "role": "user",
                        "content": formatted_prompt
                    }
                ]
            }
            
            if 'stopSequences' in inference_config:
                body['stop_sequences'] = inference_config['stopSequences']
            
            response = bedrock_runtime.invoke_model_with_response_stream(
                modelId=model_id,
                body=json.dumps(body)
            )
            
            return StreamingHttpResponse(
                stream_debate_response(response),
                content_type='text/event-stream'
            )
        
        # CHAT 템플릿 처리 (필요시)
        elif template_type == 'CHAT':
            # ... (prompt/views.py의 CHAT 로직 복사)
            pass
        
        else:
            raise ValueError(f"Unsupported template type: {template_type}")
        
    except Exception as e:
        logger.error(f"Debate topics error: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return StreamingHttpResponse(
            [sse_event({'type': 'error', 'message': str(e)})],
            content_type='text/event-stream'
        )

def stream_debate_response(response):
    """토픽 추천 스트리밍 응답"""
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