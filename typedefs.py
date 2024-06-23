"""Type definitions"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ChatResult:
    success: bool
    text_response: str
    # TODO: switch stats to tokens instead of words!!!
    words_sent: int
    words_received: int


class Llm:
    def chat(
        self,
        message: str,
        system_message: Optional[str])\
            -> ChatResult:
        pass
