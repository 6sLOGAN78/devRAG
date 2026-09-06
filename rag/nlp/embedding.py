import abc
import logging
from typing import List, Optional

import litellm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

class EmbeddingError(Exception): 
    pass

class EmbeddingDimensionError(EmbeddingError): 
    pass

class EmbeddingConfig:
    def __init__(
        self,
        provider: str,
        model: str,
        dimension: int,
        batch_size: int = 100,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.provider = provider
        self.model = model
        self.dimension = dimension
        self.batch_size = batch_size
        self.api_key = api_key
        self.base_url = base_url

class BaseEmbeddingProvider(abc.ABC):
    @abc.abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        pass

class LiteLLMProvider(BaseEmbeddingProvider):
    def __init__(self, config: EmbeddingConfig):
        self.config = config
        
    @retry(
        retry=retry_if_exception_type((
            litellm.RateLimitError, 
            litellm.APIConnectionError, 
            litellm.APIError,
            litellm.Timeout
        )),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(5)
    )
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        try:
            response = litellm.embedding(
                model=self.config.model,
                input=texts,
                api_key=self.config.api_key,
                api_base=self.config.base_url
            )
            # Ensure ordering by the 'index' provided by the provider's response
            sorted_data = sorted(response.data, key=lambda x: x['index'])
            vectors = [item['embedding'] for item in sorted_data]
            return vectors
        except Exception as e:
            logger.error(f"LiteLLM embedding failed for model {self.config.model}: {e}")
            raise

class LocalHFProvider(BaseEmbeddingProvider):
    def __init__(self, config: EmbeddingConfig):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError("sentence-transformers is required for local huggingface provider")
            
        self.config = config
        # Device is automatically chosen by sentence-transformers unless specified
        # Model is loaded once at initialization, tied to this provider instance lifecycle.
        self.model_instance = SentenceTransformer(config.model)
        
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # sentence_transformers natively encodes text batches in order
        embeddings = self.model_instance.encode(texts, batch_size=self.config.batch_size, show_progress_bar=False)
        return embeddings.tolist()

class EmbeddingEngine:
    """
    Embedding Engine converts document/chunk text into dense floating-point vectors.
    Supports provider-neutral batching, validation, and retry mechanics.
    """
    def __init__(self, config: EmbeddingConfig):
        self.config = config
        if config.provider == "litellm":
            self.provider = LiteLLMProvider(config)
        elif config.provider == "huggingface":
            self.provider = LocalHFProvider(config)
        else:
            raise ValueError(f"Unsupported embedding provider: {config.provider}")
            
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Embeds a list of texts into dense vectors.
        Splits into batches, processes, and reassembles results guaranteeing order.
        Validates dimensions of the resulting vectors.
        """
        if not texts:
            return []
            
        results = []
        for i in range(0, len(texts), self.config.batch_size):
            batch = texts[i:i + self.config.batch_size]
            
            try:
                batch_vectors = self.provider.embed_batch(batch)
            except Exception as e:
                raise EmbeddingError(f"Failed to embed batch: {e}") from e
            
            if len(batch_vectors) != len(batch):
                raise EmbeddingError(f"Expected {len(batch)} vectors, got {len(batch_vectors)}")
                
            for v in batch_vectors:
                if len(v) != self.config.dimension:
                    raise EmbeddingDimensionError(
                        f"Expected dimension {self.config.dimension}, got {len(v)} for model {self.config.model}"
                    )
                    
            results.extend(batch_vectors)
            
        return results
