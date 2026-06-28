from dataclasses import dataclass, field
from typing import List


@dataclass
class BinderNode:
    uuid: str
    type: str
    title: str
    created: str
    modified: str
    include_in_compile: bool
    children: List['BinderNode'] = field(default_factory=list)

    def __getitem__(self, key):
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key, default=None):
        if hasattr(self, key):
            val = getattr(self, key)
            if val is not None:
                return val
        return default

    def __contains__(self, key):
        return hasattr(self, key)

    def keys(self):
        return ["uuid", "type", "title", "created", "modified", "include_in_compile", "children"]

@dataclass
class SceneFiles:
    text: str
    notes: str
    synopsis: str

    def __getitem__(self, key):
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key, default=None):
        if hasattr(self, key):
            val = getattr(self, key)
            if val is not None:
                return val
        return default

    def __contains__(self, key):
        return hasattr(self, key)

    def keys(self):
        return ["text", "notes", "synopsis"]
