"""One bounded configured-model request; no source text or model response logging."""
from rag.chunking.errors import ChunkTooLong
from rag.chunking.resume import MAX_INPUT_CHARS, MAX_INPUT_TOKENS
from rag.nlp.token_count import count_tokens
from rag.parsers.errors import FileTooLarge
from rag.prompts.enrichment import RESUME_SYSTEM, resume_prompt


def resume_completion(bundle, texts):
    if len(texts) > 128 or sum(len(s) for s in texts) > MAX_INPUT_CHARS or sum(count_tokens(s) for s in texts) > MAX_INPUT_TOKENS:
        raise FileTooLarge()
    prompt = resume_prompt(texts)
    if count_tokens(RESUME_SYSTEM) + count_tokens(prompt) + 2048 + 64 > bundle.context_tokens:
        raise ChunkTooLong()
    return bundle.chat(RESUME_SYSTEM,[{"role":"user","content":prompt}],{"temperature":0,"max_tokens":2048})
