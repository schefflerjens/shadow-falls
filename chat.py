"""A wrapper around ollama and our config"""

from google.generativeai import (
    configure as genai_config, GenerationConfig, GenerativeModel)
from config import Config, CommonPrompts
from logging import getLogger
from typing import Optional


logger = getLogger()


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
        logger.debug('Message object to be sent:\n%s' % messages)
        return messages

    def _get_model(self) -> GenerativeModel:
        if self.__model:
            return self.__model
        if not Chat.__GENAI_INITIALIZED:
            logger.debug('Calling genai_config()')
            genai_config()
            Chat.__GENAI_INITIALIZED = True
        gen_config = None
        if self.__temperature is not None:
            logger.debug('Setting model temperature to %s' %
                         self.__temperature)
            gen_config = GenerationConfig(temperature=self.__temperature)
        else:
            logger.debug('Using default temperature for model.')
        self.__model = GenerativeModel(self.__config.llm_model(),
                                       generation_config=gen_config)
        return self.__model

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
        response = self._get_model().generate_content(self._make_messages(message))
        if not response.text:
            logger.error('Gemini failed to respond as expeced.')
            logger.debug('Detailed response: %s' % response)
            return None
        text = response.text.rstrip()
        logger.debug('Gemini responded: %s' % text)
        return text

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
