"""
Tool 실행 핸들러
Tool 호출 결과를 프론트엔드 형식으로 변환
"""
from .definitions import TOOL_NAVIGATE_TO_PERSON


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
        return {
            "type": "tool_call",
            "action": "navigate_to_person",
            "input": tool_input
        }
    
    # 알 수 없는 Tool
    return {
        "type": "error",
        "message": f"Unknown tool: {tool_name}"
    }
