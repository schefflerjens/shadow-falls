"""Configuration related logic"""

from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from copy import copy
from logging import getLogger
from os import path
from strenum import StrEnum
from string import Template
from sys import exit
from typing import Any, Optional, Tuple
from yaml import dump, safe_load, YAMLError


logger = getLogger()


class CommonPrompts(StrEnum):
    """Common prompts found in the YAML config"""
    SMOKE_TEST = 'smoke test'
    STORY_BEAT = 'story beat'
    BEAT_SELECTION = 'beat selection'
    SUMMARIZE_STORY = 'summarize story'
    SUMMARY_SELECTION = 'summary selection'


class PropertyKeys(StrEnum):
    """Property keys used in properties.yaml"""
    CHAPTER_SNIPPET = 'snippet'
    CHAPTER_SUMMARY = 'summary'


class Persona(StrEnum):
    """LLM personas to be found in the config"""
    AUTHOR = 'author'
    EDITOR = 'editor'
    ASSISTANT = 'assistant'


class _ConfigKeys(StrEnum):
    PROMPTS = 'prompts'
    MODEL_CONFIGS = 'model_configs'
    VERSIONS_PER_BEAT = 'versions per beat'
    VERSIONS_PER_SUMMARY = 'versions per summary'
    FILE_ENCODING = 'encoding'
    STORY_STYLE = 'style'
    ALL_SETTINGS = 'settings'
    STORY_SETTINGS = 'environment'
    STORY_BEATS = 'story beats'
    STORY_CHARACTERS = 'characters'
    STORY_GENRE = 'genre'
    STORY_ITEMS_PER_BEAT = 'items per beat'
    STORY_WORDS_PER_BEAT = 'words per beat'
    STORY_PERSPECTIVE = 'perspective'
    STORY_TENSE = 'tense'
    STORY_PREVIOUSLY = 'previously'
    SUMMARY_LENGTH = 'words per summary'
    PREVIOUS_LENGTH = 'words from last chapter'


def _chapter_path(namespace: Namespace, chapter: int) -> str:
    assert chapter <= namespace.chapter
    return path.join(namespace.project, str(chapter))


def _properties_path(namespace: Namespace) -> str:
    return path.join(namespace.project, 'properties.yaml')


def _load_yaml(path: str, encoding: str) -> Optional[Any]:
    with open(path, encoding=encoding) as stream:
        try:
            return safe_load(stream)
        except YAMLError as err:
            logger.exception(err)
            return None


def parse_flags() -> Namespace:
    """Parses commandline flags, validates and and returns them"""

    # Parse the args
    parser = ArgumentParser()
    parser.add_argument('-p', '--project', help='root folder of the project',
                        required=True)
    parser.add_argument('-c', '--chapter',
                        help='Number of chapter to work on, starts with 1',
                        required=True, type=int)
    parser.add_argument('-a', '--action',
                        help='What action to perform',
                        required=True,
                        choices=['WRITE_DRAFT', 'PRINT_CONFIG', 'SMOKE_TEST',
                                 'UPDATE_METADATA', 'NEW_CHAPTER'])
    parser.add_argument('-o', '--output',
                        help='Name of the file to write output to. '
                             'Defaults to out.txt.',
                        default='out.txt')
    parser.add_argument('-i', '--infile',
                        help='Name of text files to be read, '
                             'for example an edited chapter. '
                             'Defaults to edited.txt',
                        default='edited.txt')
    parser.add_argument('-f', '--force_overwrite',
                        action=BooleanOptionalAction,
                        help='If set, overwrite the existing output file.',
                        default=False)
    parser.add_argument('-l', '--log_file',
                        help='If set, log verbose info to this file.',
                        default='')
    args = parser.parse_args()

    # Validate that project folders exist
    if not path.exists(args.project):
        exit('Project path does not exist: %s' % args.project)
    if (args.chapter < 1):
        exit('Chapter should be a positive number, was %s' % args.chapter)
    chapter_range = (args.chapter
                     if args.action == 'NEW_CHAPTER'
                     else args.chapter + 1)
    for i in range(1, chapter_range):
        if not path.exists(_chapter_path(args, i)):
            exit('Chapter %s does not have a folder: %s' %
                 (i, _chapter_path(args, i)))

    return args


class LlmConfig:
    def __init__(self, config: dict[str, any]) -> None:
        assert 'model' in config
        self.model = str(config['model'])
        self.temperature = None
        self.persona = None
        if 'temperature' in config:
            self.temperature = int(config['temperature'])
        if 'persona' in config:
            self.persona = str(config['persona'])


class Config:

    def __merge_config(self, p: str) -> None:
        if not path.exists(p):
            self.error = 'Path does not exist: %s' % p
            return
        new_config = _load_yaml(p, self.encoding())
        if new_config is None:
            self.error = 'Could not load config: %s' % p
            return
        for k, v in new_config.items():
            if isinstance(v, dict) and k in self.__config:
                for k1, v1 in v.items():
                    if v1 == 'DELETE':
                        self.__config[k].pop(k1, None)
                    else:
                        self.__config[k][k1] = v1
            else:
                self.__config[k] = v

    def __init__(self, args: Namespace) -> None:
        """Create a config based on a set of arguments."""
        self.__config = dict()
        self.__args = args
        self.error = None
        self.__merge_config('config.yaml')
        self.__merge_config(path.join(args.project, 'config.yaml'))
        chapter_range = (args.chapter
                         if args.action == 'NEW_CHAPTER'
                         else args.chapter + 1)
        for i in range(1, chapter_range):
            self.__merge_config(
                path.join(_chapter_path(args, i), 'config.yaml'))
        # Validate that all common keys exist
        # (except for NEW_CHAPTER or SMOKE_TEST)
        if args.action not in ['NEW_CHAPTER', 'SMOKE_TEST']:
            for k in _ConfigKeys:
                if k not in self.__config:
                    self.error = 'Missing config key: %s' % k
                    self.__config = {}
                    return
            for k in CommonPrompts:
                if k not in self.__config[_ConfigKeys.PROMPTS]:
                    self.error = 'Missing common prompt: %s' % k
                    self.__config = {}
                    return
            for k in Persona:
                if k not in self.__config[_ConfigKeys.MODEL_CONFIGS]:
                    self.error = 'Missing persona for %s' % k
                    self.__config = {}
                    return
        # Load properties if they exist
        properties_path = _properties_path(args)
        if path.exists(properties_path):
            self.__properties = _load_yaml(
                _properties_path(args), self.encoding())
            if self.__properties is None:
                self.error = 'Could not load properties.yaml'
        else:
            self.__properties = {}

    def __str__(self) -> str:
        if self.error:
            return 'Invalid config: %s' % self.error
        return dump(self.__config)

    def action(self) -> str:
        return self.__args.action

    def encoding(self) -> str:
        return self.__config.get(_ConfigKeys.FILE_ENCODING, 'cp1252')

    def llm_config(self, p: Persona) -> LlmConfig:
        return LlmConfig(self.__config[_ConfigKeys.MODEL_CONFIGS][p])

    def versions_per_beat(self) -> str:
        return self.__config[_ConfigKeys.VERSIONS_PER_BEAT]

    def versions_per_summary(self) -> str:
        return self.__config[_ConfigKeys.VERSIONS_PER_SUMMARY]

    def chapter_number(self) -> int:
        return self.__args.chapter

    def setting(self) -> Optional[str]:
        result = []
        for k in self.__config[_ConfigKeys.STORY_SETTINGS]:
            if k not in self.__config[_ConfigKeys.ALL_SETTINGS]:
                logger.warning(
                    'Could not find a description for "%s" in settings.' % k)
                return None
            result.append('%s: %s\n' %
                          (k, self.__config[_ConfigKeys.ALL_SETTINGS][k]))
        return '\n'.join(result)

    def story_beats(self) -> list[str]:
        """Returns the combined story beat items.

          The "items per beat" setting determines how many beats
          are combined into one."""
        items = list(self.__config[_ConfigKeys.STORY_BEATS])
        items_per_beat = self.__config[_ConfigKeys.STORY_ITEMS_PER_BEAT]
        assert items_per_beat > 0
        result = []
        for i in range(0, len(items), items_per_beat):
            result.append(
                '* \n'.join(items[i: min(len(items), i + items_per_beat)]))
        return result

    def chapter_path(self) -> str:
        """Returns the path to the current chapter"""
        return _chapter_path(self.__args, self.__args.chapter)

    def previous_summary(self) -> Optional[str]:
        """Returns a summary of the previous chapter."""
        if (self.chapter_number() == 1):
            return self.__config[_ConfigKeys.STORY_PREVIOUSLY]
        else:
            return self.get_property(
                self.chapter_number() - 1,
                PropertyKeys.CHAPTER_SUMMARY,
                None)

    def output_file(self) -> Tuple[str, bool]:
        """Returns the file where to write output to and if it can be overwritten."""
        return (path.join(self.chapter_path(), self.__args.output),
                self.__args.force_overwrite)

    def input_file(self) -> str:
        """Returns the name of the input file to read from."""
        return path.join(self.chapter_path(), self.__args.infile)

    def trim_previous_chapter(self, previous_chapter: str) -> str:
        """Returns up to PREVIOUS_LENGTH words from the end of the last chapter"""
        chapter_words = previous_chapter.split()
        max_length = self.__config[_ConfigKeys.PREVIOUS_LENGTH]
        if len(chapter_words) <= max_length:
            return previous_chapter
        else:
            return ' '.join(chapter_words[-max_length:])

    def get_properties(self, chapter_number: int, default: Any = None) -> Any:
        """Returns all ties for a chapter. Lists and dicts may or may not be mutable"""
        val = self.__properties.get(str(chapter_number), default)
        if val is not None:
            return copy(val)
        else:
            return None

    def get_property(self, chapter_number: int, key: PropertyKeys, default: Any = None) -> Any:
        properties = self.get_properties(chapter_number)
        if not properties:
            return default
        return properties.get(str(key), default)

    def set_properties(self, chapter_number: int, value: Any) -> None:
        """Sets a property (does not save to disk)"""
        self.__properties[str(chapter_number)] = value

    def save_properties(self):
        with open(_properties_path(self.__args), 'w', encoding=self.encoding()) as f:
            f.write(dump(self.__properties))
            f.write('\n')

    def __customize(self, s: str, **kwargs) -> str:
        """Returns a string that is customized based on this config."""
        template = Template(s)
        values = dict()
        # Add simple key/value pairs
        for key in _ConfigKeys:
            value = self.__config[key]
            if not isinstance(value, dict) and not isinstance(value, list):
                values[str(key).replace(' ', '_')] = value
        # Add characters
        characters = ['%s: %s' % (k, v) for k, v in
                      self.__config[_ConfigKeys.STORY_CHARACTERS].items()]
        values['characters'] = '\n'.join(characters)
        # Add kwargs
        for k, v in kwargs.items():
            values[str(k).replace(' ', '_')] = v
        # Substitute values, normalize whitespace, and return
        return ' '.join(template.substitute(values).split())

    def prompt(self, prompt_name: CommonPrompts, **kwargs) -> str:
        """Returns a prompt that is customized based on this config.

        This method allows value subsitution: for example, having "${style}
        in the prompt will lookup and replace the value with the "style"
        entry from the config.yaml.

        Parameters
        ----------
        prompt_name: CommonPrompts
          one of the predefined prompt names to look up
        **kwargs:
          additional key/value string pairs to add for template substitution

        """
        return self.__customize(
            self.__config[_ConfigKeys.PROMPTS][prompt_name], **kwargs)

    def persona(self, config: LlmConfig) -> Optional[str]:
        """Returns the persona prompt for a given config"""
        if config.persona:
            return self.__customize(config.persona)
        else:
            return None
