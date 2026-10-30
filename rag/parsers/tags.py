"""Bounded normalized tag features; ranking keys are data, never engine field expressions."""
from dataclasses import dataclass
import math
import unicodedata

TAG_FIELD = "tag_feas"  # Existing Elasticsearch *_feas template is rank_features.
TAG_LABEL_FIELD = "tags_kwd"
MAX_TAGS = 32


def tag_label(value):
    if not isinstance(value,str):
        raise ValueError("invalid tag label")
    label=" ".join(unicodedata.normalize("NFKC",value).casefold().split())
    if not label or len(label)>64 or any(ord(c)<32 or c in ".\\/" for c in label):
        raise ValueError("invalid tag label")
    return label


def normalize_tags(weights, *, limit=MAX_TAGS):
    if type(limit) is not int or not 1<=limit<=8192:
        raise ValueError("invalid tag limit")
    if not isinstance(weights,dict) or len(weights)>max(128,limit):
        raise ValueError("invalid tag weights")
    merged={}
    for label,value in weights.items():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError("invalid tag weight")
        key=tag_label(label)
        if value:
            merged[key]=merged.get(key,0.0)+float(value)
    if len(merged)>limit:
        raise ValueError("too many tags")
    norm=math.hypot(*merged.values())
    if not math.isfinite(norm):
        raise ValueError("invalid tag weight")
    return {key:merged[key]/norm for key in sorted(merged)} if norm else {}


@dataclass(frozen=True)
class TagFeature:
    label: str
    weight: float

    def __post_init__(self):
        if tag_label(self.label)!=self.label or isinstance(self.weight,bool) or not isinstance(self.weight,(int,float)) or not math.isfinite(self.weight) or not 0<self.weight<=1:
            raise ValueError("invalid tag feature")
