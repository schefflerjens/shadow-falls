"""A wrapper around LLMs, customized for our config"""

from config import Config, CommonPrompts, Persona
from gemini import Gemini
from logging import getLogger
from typedefs import Llm, ChatResult
from typing import Optional


logger = getLogger()


class Chat:
    """Represents a configured interaction with an LLM"""

    __GENAI_INITIALIZED = False

    _words_sent = {}
    _words_received = {}

    @staticmethod
    def words_sent(p: Persona) -> int:
        return Chat._words_sent.get(p, 0)

    @staticmethod
    def words_received(p: Persona) -> int:
        return Chat._words_received.get(p, 0)

    def __init__(self, config: Config, persona: Persona) -> None:
        self.__config = config
        self.__persona = persona
        self.__system_message = None

    def __get_model(self) -> Llm:
        # TODO: support Claude
        return Gemini(self.__config.llm_config(self.__persona))

    def __update_stats(self, result: ChatResult) -> None:
        Chat._words_sent[self.__persona] = Chat._words_sent.get(
            self.__persona, 0) + result.words_sent
        Chat._words_received[self.__persona] = (
            Chat._words_received.get(
                self.__persona, 0) + result.words_received)

    def set_system_message(self, message: Optional[str]) -> None:
        """Append a non-empty system message to initialize the chat."""
        self.__system_message = message

    def chat(self, message: str) -> Optional[str]:
        """Asks a question and returns the response.

        Mostly used for debugging.
        The 'chat" method is usually more convenient.
        """
        logger.debug("Sending chat to %s LLM: %s" % (self.__persona, message))
        response = self.__get_model().chat(message, self.__system_message)
        self.__update_stats(response)
        if response.success:
            logger.debug('LLM responded: %s' % response.text_response)
            return response.text_response
        else:
            logger.error('LLM failed to respond as expected.')
            return None

    def smoke_test(self) -> str:
        """ Sends a test message to the LLM that we know the response to.

        Returns:
          str: Error string if the test failed, empty string otherwise
        """
        if self.__config.error:
            return 'Invalid config. %s' % self.__config.error
        test_message = self.__config.prompt(CommonPrompts.SMOKE_TEST)
        response = self.__get_model().chat(test_message, None)
        self.__update_stats(response)
        if response.success:
            if response.text_response == 'OK':
                return ''
            else:
                return ('Smoke test failed: llm was expected '
                        'to return "OK", got: "%s"'
                        % response.text_response)
        else:
            return 'LLM failed to respond'
