"""Verified local CPU ASR with bounded in-memory WAV/MP3 decoding."""

import io
import json
import re
from pathlib import Path

from deepdoc.model_runtime import NativeError, verify_file
from rag.parsers.audio_segments import MAX_AUDIO_SECONDS, MAX_SEGMENTS, transcript_of

MODEL_NAME = "faster-whisper-tiny"
MAX_AUDIO_BYTES = 16 * 1024 * 1024
SAMPLE_RATE = 16000


def decode_audio(content):
    import av
    import numpy as np

    if not content or len(content) > MAX_AUDIO_BYTES:
        raise NativeError("input_too_large", 413)
    # Force local byte formats. No playlist, protocol or resource URL is accepted.
    if content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        format_name = "wav"
    elif content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 255 and content[1] & 224 == 224):
        format_name = "mp3"
    else:
        raise NativeError("invalid_audio")
    samples = []
    count = 0
    try:
        with av.open(io.BytesIO(content), mode="r", format=format_name, options={"protocol_whitelist": "pipe"}) as container:
            if len(container.streams.audio) != 1:
                raise NativeError("invalid_audio")
            stream = container.streams.audio[0]
            stream.thread_type = "NONE"
            if stream.duration is not None and float(stream.duration * stream.time_base) > MAX_AUDIO_SECONDS + 0.1:
                raise NativeError("input_too_large", 413)
            resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
            for frame in container.decode(audio=0):
                if frame.samples > SAMPLE_RATE * MAX_AUDIO_SECONDS * 12 or len(frame.layout.channels) > 8:
                    raise NativeError("input_too_large", 413)
                for converted in resampler.resample(frame):
                    count += converted.samples
                    if count > SAMPLE_RATE * MAX_AUDIO_SECONDS:
                        raise NativeError("input_too_large", 413)
                    samples.append(converted.to_ndarray().reshape(-1))
            for converted in resampler.resample(None):
                count += converted.samples
                if count > SAMPLE_RATE * MAX_AUDIO_SECONDS:
                    raise NativeError("input_too_large", 413)
                samples.append(converted.to_ndarray().reshape(-1))
    except NativeError:
        raise
    except Exception:
        raise NativeError("invalid_audio") from None
    if count < SAMPLE_RATE // 4:
        raise NativeError("no_readable_text")
    audio = np.concatenate(samples).astype(np.float32) / 32768.0
    if float(np.sqrt(np.mean(audio * audio))) < 0.0001:
        raise NativeError("no_readable_text")
    return audio


class ASR:
    def __init__(self, directory: Path):
        manifest = json.loads(Path(__file__).with_name("asr-model.json").read_text())
        self.revision = manifest["revision"]
        for name, item in manifest["files"].items():
            verify_file(directory / name, item["sha256"], item["bytes"])
        from faster_whisper import WhisperModel

        self.model = WhisperModel(str(directory), device="cpu", compute_type="int8", cpu_threads=2, num_workers=1, local_files_only=True)

    def process(self, content, options):
        if set(options) - {"language", "probe"} or type(options.get("probe", False)) is not bool:
            raise NativeError("invalid_options")
        language = options.get("language")
        if language is not None and (not isinstance(language, str) or not re.fullmatch(r"[a-z]{2,3}", language)):
            raise NativeError("invalid_options")
        if options.get("probe"):
            return {"schema_version": 1, "ready": True, "model": MODEL_NAME, "revision": self.revision}
        audio = decode_audio(content)
        duration = len(audio) / SAMPLE_RATE
        segments, info = self.model.transcribe(audio, language=None, beam_size=5, best_of=1, temperature=0, vad_filter=False, condition_on_previous_text=False, word_timestamps=False)
        if language and info.language != language:
            raise NativeError("language_mismatch")
        result = []
        for segment in segments:
            if len(result) >= MAX_SEGMENTS:
                raise NativeError("output_too_large", 413)
            if segment.no_speech_prob > 0.6 or not segment.text.strip():
                continue
            result.append({"start": float(segment.start), "end": min(duration, float(segment.end)), "text": segment.text.strip()})
        if not result:
            raise NativeError("no_readable_text")
        try:
            return transcript_of({"schema_version": 1, "duration": duration, "language": info.language, "segments": result})
        except ValueError:
            raise NativeError("invalid_native_result", 502) from None
