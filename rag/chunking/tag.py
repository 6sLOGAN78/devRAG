"""Tag chunks retain original text/geometry and add normalized source-term frequency features."""
from collections import Counter
from dataclasses import dataclass,replace
from rag.chunking.naive import NaiveConfig, chunk as partition
from rag.nlp.tokenizer import tokenize
from rag.parsers.tags import TagFeature, normalize_tags


@dataclass(frozen=True)
class TagConfig:
    chunk_token_num: int = 512
    tag_top_n: int = 8

    def __post_init__(self):
        if type(self.chunk_token_num) is not int or not 1<=self.chunk_token_num<=8192:
            raise ValueError("invalid chunk size")
        if type(self.tag_top_n) is not int or not 1<=self.tag_top_n<=32:
            raise ValueError("invalid tag count")


def tag_weights(text, top_n=8):
    if type(top_n) is not int or not 1<=top_n<=32:
        raise ValueError("invalid tag count")
    counts=Counter(word for word in tokenize(text) if len(word)<=64 and any(c.isalpha() for c in word))
    chosen=sorted(counts,key=lambda word:(-counts[word],word))[:top_n]
    return normalize_tags({word:counts[word] for word in chosen})


def chunk(blocks,cfg):
    for item in partition(blocks,NaiveConfig(chunk_token_num=min(cfg.chunk_token_num,8191),delimiter="\n",overlapped_percent=0)):
        weights=tag_weights(item.text,cfg.tag_top_n)
        yield replace(item,tags=tuple(TagFeature(label,weight) for label,weight in weights.items()))
