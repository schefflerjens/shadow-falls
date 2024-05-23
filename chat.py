"""A wrapper around ollama and our config"""

from google.generativeai import (
    configure as genai_config, GenerationConfig, GenerativeModel)
from collections.abc import Iterator
from config import Config, CommonPrompts
from typing import Any, Optional, Mapping, Union


class Chat:
    """Represents a configured interaction with an LLM"""

    __GENAI_INITIALIZED = False

    def __init__(self, config: Config) -> None:
        self.__config = config
        self.__system_messages = []
        self.__chat_history = []
        self.__temperature = None
        self.__model = None

    def __copy__(self):
        result = Chat(self.__config)
        result.__system_messages.extend(self.__system_messages)
        result.__chat_history.extend(self.__chat_history)
        return result

    def __str__(self) -> str:
        """Returns a history for the chat."""
        messages = []
        messages.extend(self.__system_messages)
        messages.extend(self.__chat_history)
        return '\n'.join([str(m) for m in messages])

    def _make_messages(self, message: str) -> list[dict[str, str]]:
        """Creates a list of messages we can send to an LLM."""
        assert message, 'Message must be non-empty'
        messages = []
        messages.extend(self.__system_messages)
        messages.extend(self.__chat_history)
        messages.append({'role': 'user', 'parts': [{'text': message}]})
        return messages

    def _get_first_response(
            self, result: Union[Mapping[str, Any], Iterator[Mapping[str, Any]]]
    ) -> Optional[str]:
        """Extracts the text response from an LLM query."""
        if 'message' in result and 'content' in result['message']:
            return result['message']['content']
        else:
            return None

    def set_temperature(self, temperature: int) -> None:
        """Sets the temperature the LLK should use"""
        self.__temperature = temperature

    def add_system_message(self, message: str) -> None:
        """Append a non-empty system message to initialize the chat."""
        assert message, 'Message must be non-empty'
        assert not self.__chat_history, 'Cannot set messages after chat has started'
        self.__system_messages.append(
            # TODO: in other LLMs, the role would be 'system'. What's the best fit in Gemini?
            {'role': 'user', 'parts': [{'text': message}]})

    def chat(self, message: str) -> Optional[str]:
        """Asks a question and returns the response.

        Mostly used for debugging, the 'chat" method is usually more convenient.
        """
        if not Chat.__GENAI_INITIALIZED:
            genai_config()
            Chat.__GENAI_INITIALIZED = True
        gen_config = None
        if self.__temperature is not None:
            gen_config = GenerationConfig(temperature=self.__temperature)
        if not self.__model:
            self.__model = GenerativeModel(self.__config.llm_model(),
                                           generation_config=gen_config)
        response = self.__model.generate_content(self._make_messages(message))
        if response.text:
            return response.text.rstrip()
        # TODO: express the error somehow?
        return None

    def smoke_test(self) -> str:
        """ Sends a test message to the LLM that we know the response to.

        Returns:
          str: Error string if the test failed, empty string otherwise
        """
        assert not self.__system_messages, 'Cannot run smoke test with system messages'
        assert not self.__chat_history, 'Cannot run smoke test after chat has started'
        if self.__config.error:
            return 'Invalid config. %s' % self.__config.error
        test_message = self.__config.prompt(CommonPrompts.SMOKE_TEST)
        test_response = self.chat(test_message)
        self.__chat_history = []
        if (test_response != 'OK'):
            return ('Smoke test failed: llm was expected to return "OK", got: "%s"'
                    % test_response)
        return ''
