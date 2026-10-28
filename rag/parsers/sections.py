"""Bounded source section labels; archive paths are evidence, never filesystem input."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    path: tuple[str, ...]
    source_path: str = ""

    def __post_init__(self):
        if not isinstance(self.path, tuple) or len(self.path) > 32 or any(not isinstance(s, str) or not s.strip() or len(s) > 1024 for s in self.path):
            raise ValueError("invalid section path")
        if not isinstance(self.source_path, str) or len(self.source_path) > 4096 or "\x00" in self.source_path:
            raise ValueError("invalid source path")
