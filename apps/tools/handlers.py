"""
Tool 실행 핸들러
Tool 호출 결과를 프론트엔드 형식으로 변환
"""
import logging
from typing import Optional
from .definitions import TOOL_NAVIGATE_TO_PERSON

logger = logging.getLogger(__name__)


def get_character_info_from_db(person_name: str) -> Optional[dict]:
    """
    DB에서 캐릭터 이름으로 정보 조회
    """
    from apps.prompt.models import AIPerson
    
    try:
        # 1. 정확한 이름 매칭
        ai_person = AIPerson.objects.filter(name=person_name).first()
        
        # 2. 정확한 매칭 실패 시 부분 매칭 시도
        if not ai_person:
            ai_person = AIPerson.objects.filter(name__icontains=person_name).first()
        
        # 3. 그래도 없으면 역방향 검색 (입력값이 이름에 포함되어 있는지)
        if not ai_person:
            for person in AIPerson.objects.all():
                if person.name in person_name:
                    ai_person = person
                    break
        
        if ai_person:
            logger.info(f"DB에서 캐릭터 발견: {ai_person.name} (promptId: {ai_person.promptId})")
            return {
                "promptId": ai_person.promptId,
                "characterName": ai_person.name
            }
        
        return None
        
    except Exception as e:
        logger.error(f"DB 조회 오류: {str(e)}")
        return None


def handle_tool_result(tool_name: str, tool_input: dict) -> dict:
    """
    Tool 실행 결과를 프론트엔드가 처리할 수 있는 형식으로 변환
    
    Args:
        tool_name: 호출된 Tool 이름
        tool_input: Tool 입력 파라미터
    
    Returns:
        프론트엔드 액션 형식의 딕셔너리
    """
    if tool_name == TOOL_NAVIGATE_TO_PERSON:
        person_name = tool_input.get("person_name", "")
        character_info = get_character_info_from_db(person_name)
        
        if character_info:
            logger.info(f"캐릭터 매핑 성공: {person_name} → {character_info['promptId']}")
            return {
                "type": "tool_call",
                "tool_name": "navigate_to_character_chat",
                "parameters": {
                    "promptId": character_info["promptId"],
                    "characterName": character_info["characterName"]
                }
            }
        else:
            logger.warning(f"캐릭터 매핑 실패: {person_name}")
            return {
                "type": "error",
                "message": f"'{person_name}' 캐릭터를 찾을 수 없습니다."
            }
    
    # 알 수 없는 Tool
    return {
        "type": "error",
        "message": f"Unknown tool: {tool_name}"
    }

