class ParserError(Exception):
    """Base exception for all DeepDoc parser errors."""

class InvalidInputError(ParserError):
    """Raised when the input file is invalid or missing."""

class UnsupportedFormatError(ParserError):
    """Raised when the parser does not support the given format."""

class ParsingFailureError(ParserError):
    """Raised when the parser encounters an internal error while processing."""
