"""Various utility functions."""

from logging import basicConfig, getLogger, Formatter, StreamHandler, \
    INFO, DEBUG
from typing import Optional


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
    first_part = first_part.strip()
    second_part = second_part.strip()
    for i in range(len(first_part)):
        if second_part.startswith(first_part[i:]):
            return second_part[(len(first_part) - i):].strip()
    return second_part.strip()


def last_sentences(s: str, i: int) -> str:
    """Find the last i sentences in a string str"""
    s = s.strip()
    sentences = [t.strip() for t in s.split('.') if t.strip()]
    joined = '. '.join(sentences[-i:])
    if joined:
        return joined + '.'
    else:
        return ''
