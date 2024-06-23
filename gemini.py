"""A wrapper around gemini, customized for our config"""

from google.api_core.exceptions import ResourceExhausted
from google.generativeai import (
    configure as genai_config, GenerationConfig, GenerativeModel)
from google.generativeai.types.safety_types import HarmCategory
from config import LlmConfig
from logging import getLogger
from time import sleep
from typedefs import Llm, ChatResult
from typing import Optional


logger = getLogger()


class Gemini(Llm):
    """Represents an interaction with Gemini"""

    __GENAI_INITIALIZED = False

    def __init__(self, config: LlmConfig) -> None:
        self.__config = config
        self.__model = None

    def __create_payload(self,
                         message: str,
                         system_message: Optional[str] = None)\
            -> list[dict[str, str]]:
        """Creates a list of messages we can send to an LLM."""
        assert message, 'Message must be non-empty'
        messages = []
        if system_message:
            messages.append(
                # TODO: in other LLMs, the role would be 'system'.
                # What's the best fit in Gemini?
                {'role': 'user', 'parts': [{'text': message}]})
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
        if not Gemini.__GENAI_INITIALIZED:
            logger.debug('Calling genai_config()')
            genai_config()
            Gemini.__GENAI_INITIALIZED = True
        gen_config = None
        if self.__config.temperature is not None:
            logger.debug('Setting model temperature to %s' %
                         self.__config.temperature)
            gen_config = GenerationConfig(
                temperature=self.__config.temperature)
        else:
            logger.debug('Using default temperature for model.')
        self.__model = GenerativeModel(self.__config.model,
                                       generation_config=gen_config,
                                       safety_settings=self.__safety_settings()
                                       )
        return self.__model

    def __count_words(self, payload: list[dict[str, any]]) -> int:
        count = 0
        for i in payload:
            if 'parts' not in i:
                continue
            for p in i['parts']:
                if 'text' not in p:
                    continue
                count += len(p['text'].split())
        return count

    def chat(
        self,
        message: str,
        system_message: Optional[str])\
            -> ChatResult:
        payload = self.__create_payload(message, system_message)
        # see https://www.googlecloudcommunity.com/\
        # gc/AI-ML/Gemini-Pro-Quota-Exceeded/m-p/693185
        sleep_count = 0
        sleep_time = 2
        words_sent = 0
        words_received = 0
        payload_wordcount = self.__count_words(payload)
        while True:
            try:
                words_sent += payload_wordcount
                response = self.__get_model().generate_content(payload)
                if response and response.text:
                    words_received += len(response.text.split())
            except ResourceExhausted as re:
                logger.debug(
                    'ResourceExhausted exception occurred '
                    'while talking to gemini: %s' % re)
                sleep_count += 1
                if sleep_count > 5:
                    logger.warn(
                        'ResourceExhausted exception occurred '
                        '5 times in a row. Exiting.')
                    return ChatResult(
                        success=False,
                        text_response=None,
                        words_sent=words_sent,
                        words_received=words_received
                    )
                logger.info(
                    'Too many requests, backing off for %s seconds'
                    % sleep_time)
                sleep(sleep_time)
                sleep_time *= 2
            else:
                return ChatResult(
                    success=True,
                    text_response=response.text.rstrip(),
                    words_sent=words_sent,
                    words_received=words_received
                )
