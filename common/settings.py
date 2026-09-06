import os
import re
import yaml
from pydantic import BaseModel, ValidationError, Field

class MySQLConfig(BaseModel):
    host: str
    port: int = Field(gt=0, le=65535)
    user: str
    password: str
    db: str

class RedisConfig(BaseModel):
    host: str
    port: int = Field(gt=0, le=65535)
    db: int

class MinIOConfig(BaseModel):
    endpoint: str
    access_key: str
    secret_key: str

class InfinityConfig(BaseModel):
    host: str
    port: int = Field(gt=0, le=65535)

class NATSConfig(BaseModel):
    endpoints: str

class RAGFlowConfig(BaseModel):
    go_port: int = Field(gt=0, le=65535)
    python_port: int = Field(gt=0, le=65535)


class EmbeddingModelConfig(BaseModel):
    name: str = 'BAAI/bge-large-en-v1.5'
    dimension: int = 1024
    provider: str = 'huggingface'

class OcrModelConfig(BaseModel):
    name: str = 'paddleocr'

class LayoutModelConfig(BaseModel):
    name: str = 'yolov8'

class TsrModelConfig(BaseModel):
    name: str = 'hf-tsr'

class DefaultModelsConfig(BaseModel):
    embedding_model: EmbeddingModelConfig = EmbeddingModelConfig()
    ocr_model: OcrModelConfig = OcrModelConfig()
    layout_model: LayoutModelConfig = LayoutModelConfig()
    tsr_model: TsrModelConfig = TsrModelConfig()

class UserDefaultLLMConfig(BaseModel):
    default_models: DefaultModelsConfig = DefaultModelsConfig()

class AuthConfig(BaseModel):
    jwt_secret: str
    jwt_expiration_minutes: int
    session_ttl_minutes: int

class Config(BaseModel):
    mysql: MySQLConfig
    redis: RedisConfig
    minio: MinIOConfig
    infinity: InfinityConfig
    nats: NATSConfig
    ragflow: RAGFlowConfig
    auth: AuthConfig
    user_default_llm: UserDefaultLLMConfig = UserDefaultLLMConfig()

def expand_env(text: str) -> str:
    pattern = re.compile(r'\$\{([a-zA-Z_][a-zA-Z0-9_]*)(?::-([^}]*))?\}')
    
    def replacer(match):
        key = match.group(1)
        default_val = match.group(2) if match.group(2) is not None else ""
        val = os.environ.get(key, "")
        if val == "":
            return default_val
        return val

    return pattern.sub(replacer, text)

def load_config(path: str) -> Config:
    try:
        with open(path, 'r') as f:
            data = f.read()
    except Exception as e:
        raise RuntimeError(f"could not read config file: {e}")
        
    expanded = expand_env(data)
    try:
        parsed_yaml = yaml.safe_load(expanded)
    except Exception as e:
        raise RuntimeError(f"could not parse yaml: {e}")
        
    try:
        return Config(**parsed_yaml)
    except ValidationError as e:
        raise RuntimeError(f"configuration error: {e}")

if __name__ == "__main__":
    import sys
    try:
        cfg = load_config(sys.argv[1])
        print(cfg.model_dump_json(indent=2))
    except Exception as e:
        print(e, file=sys.stderr)
        sys.exit(1)
