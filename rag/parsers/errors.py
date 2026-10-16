"""Typed parser failures. Messages are fixed and never echo a path, a file name or file content (D-08, D-23)."""

from __future__ import annotations


class ParserError(Exception):
    code = "file_damaged"
    message = "the file could not be parsed"

    def __init__(self) -> None:
        super().__init__(self.message)


class UnsupportedType(ParserError):
    code = "unsupported_type"
    message = "this file type cannot be parsed"


class NoReadableText(ParserError):
    code = "no_readable_text"
    message = "the file has no readable text"


class FileDamaged(ParserError):
    code = "file_damaged"
    message = "the file is damaged or unreadable"


class FileTooLarge(ParserError):
    code = "file_too_large"
    message = "the file is larger than the parse limit"


class ArchiveLimitsExceeded(ParserError):
    code = "archive_limits_exceeded"
    message = "the file's internal structure exceeds the safety limits"
