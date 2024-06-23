"""A wrapper around gemini, customized for our config"""

from anthropic import Anthropic, NOT_GIVEN
from config import LlmConfig
from logging import getLogger
from typedefs import Llm, ChatResult
from typing import Optional


logger = getLogger()


class Claude(Llm):
    """Represents an interaction with Claude"""

    __GENAI_INITIALIZED = False

    def __init__(self, config: LlmConfig) -> None:
        self.__config = config
        self.__client = Anthropic()

    def chat(
        self,
        message: str,
        system_message: Optional[str])\
            -> ChatResult:
        response = self.__client.messages.create(
            max_tokens=3000,  # TODO: make configurable
            messages=[{
                "role": "user",
                "content": message,
            }],
            system=system_message if system_message else NOT_GIVEN,
            model=self.__config.model,
            temperature=self.__config.temperature or 1.0
        )
        # TODO: switch stats to tokens instead of words!!!
        words_sent = response.usage.input_tokens * 3 / 4
        words_received = response.usage.output_tokens * 3 / 4
        if response.stop_reason and response.stop_reason != 'end_turn':
            logger.debug('Request to claude failed: %s' % response)
            return ChatResult(
                success=False,
                text_response=response.stop_reason,
                words_sent=words_sent,
                words_received=words_received
            )

        text_snippets = [
            s.text for s in response.content
            if s.type == 'text'
        ]
        return ChatResult(
            success=True,
            text_response='\n'.join(text_snippets),
            words_sent=words_sent,
            words_received=words_received
        )
