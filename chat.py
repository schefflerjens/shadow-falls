"""A wrapper around gemini, customized for our config"""

from google.api_core.exceptions import ResourceExhausted
from google.generativeai import (
    configure as genai_config, GenerationConfig, GenerativeModel)
from google.generativeai.types.generation_types import GenerateContentResponse
from google.generativeai.types.safety_types import HarmCategory
from config import Config, CommonPrompts, Persona
from logging import getLogger
from time import sleep
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
        self.__system_messages = []
        self.__chat_history = []
        self.__model = None
        self.__persona = persona

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

    def __make_messages(self, message: str) -> list[dict[str, str]]:
        """Creates a list of messages we can send to an LLM."""
        assert message, 'Message must be non-empty'
        messages = []
        messages.extend(self.__system_messages)
        messages.extend(self.__chat_history)
        messages.append({'role': 'user', 'parts': [{'text': message}]})
        logger.debug('Message object to be sent:\n%s' % messages)
        return messages

    def __safety_settings(self) -> list[dict[str, str]]:
        # For safety settings, see also https://tinyurl.com/442f8hpv
        result = []
        for c in [
            HarmCategory.HARM_CATEGORY_HARASSMENT,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        ]:
            result.append({
                "category": c.name,
                "threshold": "BLOCK_NONE",
            })
        return result

    def __get_model(self) -> GenerativeModel:
        if self.__model:
            return self.__model
        if not Chat.__GENAI_INITIALIZED:
            logger.debug('Calling genai_config()')
            genai_config()
            Chat.__GENAI_INITIALIZED = True
        llm_config = self.__config.llm_config(self.__persona)
        gen_config = None
        if llm_config.temperature is not None:
            logger.debug('Setting model temperature to %s' %
                         llm_config.temperature)
            gen_config = GenerationConfig(
                temperature=llm_config.temperature)
        else:
            logger.debug('Using default temperature for model.')
        self.__model = GenerativeModel(llm_config.model,
                                       generation_config=gen_config,
                                       safety_settings=self.__safety_settings()
                                       )
        return self.__model

    def add_system_message(self, message: str) -> None:
        """Append a non-empty system message to initialize the chat."""
        assert message, 'Message must be non-empty'
        assert not self.__chat_history, 'Cannot set messages '
        'after chat has started'
        self.__system_messages.append(
            # TODO: in other LLMs, the role would be 'system'.
            # What's the best fit in Gemini?
            {'role': 'user', 'parts': [{'text': message}]})

    def __count_words(self, payload: list[dict[str, any]]):
        count = 0
        for i in payload:
            if 'parts' not in i:
                continue
            for p in i['parts']:
                if 'text' not in p:
                    continue
                count += len(p['text'].split())
        return count

    def __rpc_with_retry(self, payload: list[dict[str, any]])\
            -> Optional[GenerateContentResponse]:
        # see https://www.googlecloudcommunity.com/\
        # gc/AI-ML/Gemini-Pro-Quota-Exceeded/m-p/693185
        sleep_count = 0
        sleep_time = 2
        payload_wordcount = self.__count_words(payload)
        while True:
            try:
                Chat._words_sent[self.__persona] = Chat._words_sent.get(
                    self.__persona, 0) + payload_wordcount
                response = self.__get_model().generate_content(payload)
                if response and response.text:
                    Chat._words_received[self.__persona] = (
                        Chat._words_received.get(
                            self.__persona, 0) + len(response.text.split()))
            except ResourceExhausted as re:
                logger.debug(
                    'ResourceExhausted exception occurred '
                    'while talking to gemini: %s' % re)
                sleep_count += 1
                if sleep_count > 5:
                    logger.warn(
                        'ResourceExhausted exception occurred '
                        '5 times in a row. Exiting.')
                    return None
                logger.info(
                    'Too many requests, backing off for %s seconds'
                    % sleep_time)
                sleep(sleep_time)
                sleep_time *= 2
            else:
                return response

    def chat(self, message: str) -> Optional[str]:
        """Asks a question and returns the response.

        Mostly used for debugging.
        The 'chat" method is usually more convenient.
        """
        response = self.__rpc_with_retry(self.__make_messages(message))
        if not response or not response.text:
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
        assert not self.__system_messages, \
            'Cannot run smoke test with system messages'
        assert not self.__chat_history, \
            'Cannot run smoke test after chat has started'
        if self.__config.error:
            return 'Invalid config. %s' % self.__config.error
        test_message = self.__config.prompt(CommonPrompts.SMOKE_TEST)
        test_response = self.chat(test_message)
        self.__chat_history = []
        if (test_response != 'OK'):
            return ('Smoke test failed: llm was expected '
                    'to return "OK", got: "%s"'
                    % test_response)
        return ''
