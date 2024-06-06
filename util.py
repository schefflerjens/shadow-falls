"""Various utility functions."""


def remove_overlap(first_part: str, second_part: str) -> str:
    """Returns the part of second_part that is not at the end of first_part."""
    for i in range(len(first_part)):
        if second_part.startswith(first_part[i:]):
            return second_part[(len(first_part) - i):]
    return second_part


def last_sentences(s: str, i: int) -> str:
    """Find the last i sentences in a string str"""
    end = len(s)
    if s[end - 1] == '.':
        # Ignore the period of the last sentence
        end -= 1
    for _ in range(i):
        idx = s.rfind('.', 0, end)
        if idx >= 0:
            end = idx
        if idx <= 0:
            break
    return s[(end + 1):].strip()
