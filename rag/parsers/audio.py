"""Audio bytes enter the named tenant-authorized ASR operation supplied by the worker."""

from rag.parsers.types import ParsedBlock
from rag.parsers.audio_segments import AudioSpan, transcript_of
from rag.parsers.errors import FileTooLarge
from rag.parsers.deepdoc_client import NativeUnavailable


def parse(source, report, *, page_range=None, limits=None, transcribe=None):
    if transcribe is None:
        raise NativeUnavailable()
    if source.size > 16 * 1024 * 1024:
        raise FileTooLarge()
    with source.path.open("rb") as stream:
        content = stream.read(16 * 1024 * 1024 + 1)
    if len(content) > 16 * 1024 * 1024:
        raise FileTooLarge()
    value = transcript_of(transcribe(content))
    return iter(ParsedBlock(s["text"], "audio", audio=AudioSpan(s["start"], s["end"])) for s in value["segments"])
