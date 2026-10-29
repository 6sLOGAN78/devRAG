"""Credential-free ASR over the exact operator-configured DeepDoc boundary."""

from rag.parsers.deepdoc_client import DeepDocClient, NativeUnavailable
from rag.parsers.audio_segments import transcript_of

MODEL_NAME = "faster-whisper-tiny"
MODEL_REVISION = "d90ca5fe260221311c53c58e660288d3deb8d356"


class AsrModel:
    def __init__(self, settings, model_name, api_base=None):
        if model_name != MODEL_NAME or api_base not in (None, "", "http://deepdoc:9390", settings.deepdoc.url):
            raise NativeUnavailable()
        self.client = DeepDocClient(settings.deepdoc)

    def probe(self):
        value = self.client._request("/v1/asr", b"probe", {"probe": True})
        if value != {"schema_version": 1, "ready": True, "model": MODEL_NAME, "revision": MODEL_REVISION}:
            raise NativeUnavailable()

    def transcribe(self, content, language=None):
        if type(content) is not bytes or not content or len(content) > 16 * 1024 * 1024:
            from rag.parsers.errors import FileTooLarge
            raise FileTooLarge()
        result = self.client._request("/v1/asr", content, {} if language is None else {"language": language})
        try:
            return transcript_of(result)
        except ValueError:
            raise NativeUnavailable() from None
