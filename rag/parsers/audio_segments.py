"""Pure timestamp evidence shared across native, worker and source views."""

import math
from dataclasses import dataclass

MAX_AUDIO_SECONDS = 60.0
MAX_SEGMENTS = 256


@dataclass(frozen=True)
class AudioSpan:
    start: float
    end: float

    def __post_init__(self):
        if any(type(n) not in (int, float) or not math.isfinite(n) for n in (self.start, self.end)) or not 0 <= self.start < self.end <= MAX_AUDIO_SECONDS:
            raise ValueError("invalid audio timestamp")

    def to_dto(self):
        return {"start": self.start, "end": self.end}


def audio_of(row):
    if row.get("audio_start_flt") is None:
        return None
    try:
        return AudioSpan(row["audio_start_flt"], row["audio_end_flt"]).to_dto()
    except (ValueError, TypeError, KeyError):
        return None


def transcript_of(value):
    if not isinstance(value, dict) or set(value) != {"schema_version", "duration", "language", "segments"} or type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("invalid transcript")
    duration, language, segments = value["duration"], value["language"], value["segments"]
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= MAX_AUDIO_SECONDS or not isinstance(language, str) or not 2 <= len(language) <= 8:
        raise ValueError("invalid transcript")
    if not isinstance(segments, list) or not 0 < len(segments) <= MAX_SEGMENTS:
        raise ValueError("invalid transcript")
    previous = 0
    total = 0
    for segment in segments:
        if not isinstance(segment, dict) or set(segment) != {"start", "end", "text"}:
            raise ValueError("invalid transcript")
        span = AudioSpan(segment["start"], segment["end"])
        text = segment["text"]
        if span.start < previous or span.end > duration or not isinstance(text, str) or not text.strip() or len(text) > 4096:
            raise ValueError("invalid transcript")
        previous = span.end
        total += len(text.encode())
        if total > 65536:
            raise ValueError("invalid transcript")
    return value
