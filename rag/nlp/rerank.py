import logging
from typing import List, Optional
from dataclasses import dataclass
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

@dataclass
class RerankConfig:
    provider: str = "huggingface"
    model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    batch_size: int = 16
    device: Optional[str] = None
    enabled: bool = True
    max_length: int = 512

class BaseRerankProvider:
    def rerank(self, query: str, texts: List[str]) -> List[float]:
        raise NotImplementedError

class HuggingFaceRerankProvider(BaseRerankProvider):
    def __init__(self, config: RerankConfig):
        self.config = config
        self._model = None

    @property
    def model(self):
        # Lazy initialization prevents unneeded model loading
        if self._model is None:
            logger.info(f"Loading CrossEncoder model {self.config.model}")
            self._model = CrossEncoder(
                self.config.model, 
                device=self.config.device, 
                max_length=self.config.max_length
            )
        return self._model

    def rerank(self, query: str, texts: List[str]) -> List[float]:
        if not texts:
            return []
        
        pairs = [[query, text] for text in texts]
        
        try:
            scores = self.model.predict(pairs, batch_size=self.config.batch_size)
            if hasattr(scores, 'tolist'):
                return scores.tolist()
            return list(scores)
        except Exception as e:
            logger.error(f"Failed to predict cross-encoder scores: {e}")
            raise e

class RerankEngine:
    def __init__(self, config: RerankConfig):
        self.config = config
        if config.provider == "huggingface":
            self.provider = HuggingFaceRerankProvider(config)
        else:
            raise ValueError(f"Unsupported rerank provider: {config.provider}")

    def rerank_scores(self, query: str, texts: List[str]) -> List[float]:
        if not self.config.enabled:
            return [0.0] * len(texts)
        return self.provider.rerank(query, texts)
