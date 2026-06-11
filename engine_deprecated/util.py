"""Various utility functions."""

from logging import basicConfig, getLogger, Formatter, StreamHandler, \
    INFO, DEBUG
from string import whitespace
from typing import Optional

_WHITESPACE_AND_PUNCTUATION = whitespace + ',.;!'
_WHITESPACE_AND_QUOTES = whitespace + "\"'"
_WHITESPACE_AND_PUNCTATION_AND_QUOTES = _WHITESPACE_AND_PUNCTUATION + "'\""


def configure_logging(log_file: Optional[str]) -> None:
    """Set up logging to log info and above to console
       and (optionally) everything to a file."""
    if log_file:
        basicConfig(level=DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename=log_file,
                    filemode='a')
        console = StreamHandler()
        console.setLevel(INFO)
        console.setFormatter(Formatter('%(message)s'))
        getLogger('').addHandler(console)
    else:
        basicConfig(level=INFO, format='%(message)s')


def remove_overlap(first_part: str, second_part: str) -> str:
    """Eliminates overalp between two strings, returning the second part."""
    candidates = [
        first_part,
        first_part.rstrip(whitespace),
        first_part.rstrip(_WHITESPACE_AND_PUNCTUATION),
        first_part.rstrip(_WHITESPACE_AND_QUOTES),
        first_part.rstrip(_WHITESPACE_AND_PUNCTATION_AND_QUOTES),
    ]
    result = second_part
    sp_stripped = second_part.lstrip(_WHITESPACE_AND_PUNCTATION_AND_QUOTES)
    for candidate in candidates:
        for i in range(len(candidate)):
            if second_part.startswith(candidate[i:]):
                new_result = second_part[(len(candidate) - i):].strip()
                removed = second_part[0: len(candidate) - i]
                # Ignore if only quotes and whitespace get removed
                if not removed.strip(_WHITESPACE_AND_PUNCTATION_AND_QUOTES):
                    continue
                if len(new_result) < len(result):
                    result = new_result
                    break
            if sp_stripped.startswith(candidate[i:]):
                new_result = sp_stripped[(len(candidate) - i):].strip()
                removed = sp_stripped[0: len(candidate) - i]
                # Ignore if only quotes and whitespace get removed
                if not removed.strip(_WHITESPACE_AND_PUNCTATION_AND_QUOTES):
                    continue
                if len(new_result) < len(result):
                    result = new_result
                    break
    return result.strip()


def last_sentences(s: str, i: int) -> str:
    """Find the last i sentences in a string str"""
    s = s.strip()
    sentences = [t.strip() for t in s.split('.') if t.strip()]
    joined = '. '.join(sentences[-i:])
    if joined:
        return joined + '.'
    else:
        return ''
