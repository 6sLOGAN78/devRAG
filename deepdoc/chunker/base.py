from typing import List
from ..models import DocumentStructure
from .models import Chunk
import tiktoken

class TokenCounter:
    def __init__(self, model_name: str = "cl100k_base"):
        try:
            self.encoding = tiktoken.get_encoding(model_name)
        except Exception:
            self.encoding = tiktoken.get_encoding("cl100k_base")
            
    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self.encoding.encode(text))

class BaseChunker:
    def __init__(self, max_tokens: int = 500, min_tokens: int = 0, overlap_tokens: int = 0):
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.overlap_tokens = overlap_tokens
        self.token_counter = TokenCounter()
        
    def chunk(self, document: DocumentStructure) -> List[Chunk]:
        raise NotImplementedError("Chunker subclasses must implement chunk()")
