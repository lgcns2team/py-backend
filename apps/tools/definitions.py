"""
Tool 정의 모듈
AWS Bedrock Converse API에 전달할 Tool 스펙을 정의합니다.
"""

# Bedrock Converse API toolConfig 형식
TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": "navigate_to_person",
                "description": "역사 인물과 대화하는 페이지로 사용자를 이동시킵니다. 사용자가 특정 역사 인물과 대화하고 싶다고 요청할 때 사용합니다. 예: '이순신과 대화하고 싶어', '세종대왕한테 문자 보내줘', '광개토대왕이랑 얘기할래'",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "person_name": {
                                "type": "string",
                                "description": "이동할 역사 인물의 이름 (예: 이순신, 세종대왕, 광개토대왕, 을지문덕)"
                            }
                        },
                        "required": ["person_name"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "navigate_to_war",
                "description": "사용자가 특정 전쟁에 대해 묻거나 설명을 요청할 때 사용합니다. 지도에서 해당 전쟁 시점과 위치로 이동합니다.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "war_name": {
                                "type": "string",
                                "description": "전쟁 이름 (예: 임진왜란, 한국전쟁, 병자호란)"
                            },
                            "year": {
                                "type": "integer",
                                "description": "전쟁 발발 연도 (예: 1592, 1950, 1636)"
                            }
                        },
                        "required": ["war_name", "year"]
                    }
                }
            }
        }
    ]
}

# Tool 이름 상수
TOOL_NAVIGATE_TO_PERSON = "navigate_to_person"
TOOL_NAVIGATE_TO_WAR = "navigate_to_war"

# Router 시스템 프롬프트
ROUTER_SYSTEM_PROMPT = """당신은 역사 교과서 AI 도우미입니다.

사용자가 다음과 같은 요청을 하면 반드시 navigate_to_person 도구를 사용하세요:
- "XXX한테 말걸어줘", "XXX와 대화하고 싶어", "XXX에게 문자 보내줘", "XXX와 채팅 시작해줘"
- "XXX랑 얘기하고 싶어", "XXX한테 연락해줘"
- 특정 역사 인물과 직접 대화를 원하는 경우

사용자가 전쟁에 대해 물어보면 반드시 navigate_to_war 도구를 사용하여 해당 연도와 전쟁 이름을 추출하세요.

다음 경우에는 도구를 사용하지 마세요:
- "XXX에 대해 알려줘", "XXX가 뭐야?" - 정보 요청
- 전쟁을 제외한 일반적인 역사 관련 질문

도구를 사용하지 않는 경우, 간단히 "Knowledge Base에서 검색하겠습니다"라고만 답하세요.
"""
