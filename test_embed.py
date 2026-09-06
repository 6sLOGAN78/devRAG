import os
from common.settings import load_config
from rag.nlp.embedding import EmbeddingEngine, EmbeddingConfig

cfg = load_config(os.environ.get('RAGFLOW_CONFIG', 'conf/service_conf.yaml'))
model_cfg = cfg.user_default_llm.default_models.embedding_model

print(f"Testing embedding model: {model_cfg.name} (Dim: {model_cfg.dimension})")

config = EmbeddingConfig(
    provider=model_cfg.provider,
    model=model_cfg.name,
    dimension=model_cfg.dimension
)

engine = EmbeddingEngine(config)
vectors = engine.embed(["Hello world", "This is a test"])

print(f"Successfully generated {len(vectors)} vectors of dimension {len(vectors[0])}!")
