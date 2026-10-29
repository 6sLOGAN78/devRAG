"""Bounded normalized images through the existing guarded chat transport."""

import base64
from rag.llm.chat_model import LiteLLMBase
from rag.llm.errors import ModelException, LLMErrorCode

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_CAPTION_CHARS = 1024
PNG = b"\x89PNG\r\n\x1a\n"
from rag.prompts.generator import PICTURE_CAPTION_SYSTEM as CAPTION_SYSTEM


class VisionBase(LiteLLMBase):
    def describe(self, image: bytes):
        if type(image) is not bytes or not image.startswith(PNG) or len(image) > MAX_IMAGE_BYTES:
            raise ModelException(LLMErrorCode.ERROR_INVALID_REQUEST)
        url = "data:image/png;base64," + base64.b64encode(image).decode("ascii")
        text, tokens = self.chat(
            CAPTION_SYSTEM, [{"role": "user", "content": [{"type": "text", "text": "Describe this image."}, {"type": "image_url", "image_url": {"url": url}}]}], {"max_tokens": 256, "temperature": 0}
        )
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_CAPTION_CHARS:
            raise ModelException(LLMErrorCode.ERROR_INVALID_REQUEST)
        return text.strip(), tokens
