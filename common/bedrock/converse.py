"""
Bedrock Converse API Wrapper
Tool Calling을 지원하는 Converse API 클라이언트
"""
import json
import logging
from typing import Optional
from django.conf import settings
from .clients import BedrockClients

logger = logging.getLogger(__name__)


class ConverseClient:
    """Bedrock Converse API를 활용한 Tool Calling 클라이언트"""
    
    def __init__(self, model_id: str = None):
        self.client = BedrockClients.get_runtime()
        self.model_id = model_id or getattr(
            settings, 
            'BEDROCK_MODEL_ID', 
            'anthropic.claude-3-5-sonnet-20240620-v1:0'
        )
    
    def invoke_with_tools(
        self, 
        messages: list, 
        tool_config: dict, 
        system: Optional[list] = None
    ) -> dict:
        """
        Tool Calling이 가능한 Converse API 호출
        
        Args:
            messages: 대화 메시지 리스트 [{"role": "user", "content": [{"text": "..."}]}]
            tool_config: Tool 정의 {"tools": [...]}
            system: 시스템 프롬프트 [{"text": "..."}]
        
        Returns:
            {
                "type": "tool_call" | "text",
                "action": "tool_name" (tool_call인 경우),
                "input": {...} (tool_call인 경우),
                "content": "..." (text인 경우)
            }
        """
        try:
            request_params = {
                "modelId": self.model_id,
                "messages": messages,
                "toolConfig": tool_config
            }
            
            if system:
                request_params["system"] = system
            
            logger.info(f"Converse API 호출 - Model: {self.model_id}")
            response = self.client.converse(**request_params)
            
            return self._parse_response(response)
            
        except Exception as e:
            logger.error(f"Converse API 오류: {str(e)}")
            raise
    
    def _parse_response(self, response: dict) -> dict:
        """
        Converse API 응답 분석
        
        stopReason에 따라 tool_use 또는 text 응답으로 분류
        """
        stop_reason = response.get('stopReason', '')
        output = response.get('output', {})
        message = output.get('message', {})
        content_blocks = message.get('content', [])
        
        logger.info(f"Converse 응답 - stopReason: {stop_reason}")
        
        if stop_reason == 'tool_use':
            # Tool 호출 감지
            for block in content_blocks:
                if 'toolUse' in block:
                    tool_use = block['toolUse']
                    result = {
                        "type": "tool_call",
                        "action": tool_use.get('name'),
                        "input": tool_use.get('input', {})
                    }
                    logger.info(f"Tool 호출 감지: {result['action']}")
                    return result
        
        # 일반 텍스트 응답
        text_content = ""
        for block in content_blocks:
            if 'text' in block:
                text_content += block['text']
        
        return {
            "type": "text",
            "content": text_content
        }
