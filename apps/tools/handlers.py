"""
Tool 실행 핸들러
Tool 호출 결과를 프론트엔드 형식으로 변환
"""
import logging
from .definitions import TOOL_NAVIGATE_TO_PERSON

logger = logging.getLogger(__name__)

# 캐릭터 매핑 (테스트용 하드코딩 - 추후 DB 연동 예정)
CHARACTER_MAP = {
    "이순신": {
        "promptId": "X61RA20825",
        "characterName": "이순신"
    },
    # TODO: 추후 DB 연동 시 삭제
    # "세종대왕": {"promptId": "king-sejong", "characterId": "char-002", "characterName": "세종대왕"},
    # "광개토대왕": {"promptId": "gwanggaeto", "characterId": "char-003", "characterName": "광개토대왕"},
}


def get_character_info(person_name: str) -> dict | None:
    """
    캐릭터 이름으로 정보 조회
    
    TODO: 추후 DB 조회로 변경
    """
    # 정확한 매칭
    if person_name in CHARACTER_MAP:
        return CHARACTER_MAP[person_name]
    
    # 부분 매칭 (이순신 장군 → 이순신)
    for name, info in CHARACTER_MAP.items():
        if name in person_name or person_name in name:
            return info
    
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
        character_info = get_character_info(person_name)
        
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
