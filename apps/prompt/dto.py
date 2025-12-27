from dataclasses import dataclass
from typing import Literal, Dict, Any


Role = Literal["user", "assistant", "system"]


@dataclass
class MessageDTO:
    role: Role
    content: str

    @staticmethod
    def user(content: str) -> "MessageDTO":
        return MessageDTO(role="user", content=content)

    @staticmethod
    def assistant(content: str) -> "MessageDTO":
        return MessageDTO(role="assistant", content=content)

    @staticmethod
    def system(content: str) -> "MessageDTO":
        return MessageDTO(role="system", content=content)

    def to_dict(self) -> Dict[str, Any]:
        return {"role": self.role, "content": self.content}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "MessageDTO":
        return MessageDTO(role=d.get("role"), content=d.get("content", ""))
