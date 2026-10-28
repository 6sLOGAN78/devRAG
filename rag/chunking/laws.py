"""Legal chapter/section/article/item hierarchy with raw source and bounded chunks."""

from dataclasses import dataclass, replace
import re

from rag.chunking.paper import section_chunks

_CHINESE = re.compile(r"^第[零〇一二三四五六七八九十百千万萬两兩0-9]+([章节節条條项項款])(?:\s+[^\n]{1,120})?$")
_ENGLISH = re.compile(r"^(Chapter|Section|Article|Item)\s+(?:[0-9]+(?:\.[0-9]+)*|[IVXLCDM]+)(?:[.:]?\s+[^\n]{1,120})?$", re.I)
_LEVEL = {"章": 1, "节": 2, "節": 2, "条": 3, "條": 3, "项": 4, "項": 4, "款": 4, "chapter": 1, "section": 2, "article": 3, "item": 4}


@dataclass(frozen=True)
class LawsConfig:
    chunk_token_num: int = 512


def chunk(blocks, cfg: LawsConfig):
    def structure():
        for original in blocks:
            lines = original.text.splitlines() if original.kind == "text" else [original.text]
            for text in lines:
                yield from classify(replace(original, text=text))

    def classify(block):
        text = block.text.strip()
        match = (_CHINESE.fullmatch(text) or _ENGLISH.fullmatch(text)) if block.kind in {"text", "heading"} else None
        if match:
            yield replace(block, kind="heading", heading_level=_LEVEL[match[1].lower()])
        else:
            yield block

    def heading(block):
        return (block.text.strip(), block.heading_level or 1) if block.kind == "heading" else None

    yield from section_chunks(structure(), cfg, heading)
