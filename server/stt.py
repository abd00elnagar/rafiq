"""Speech-to-Text. Standalone test:  python -m server.stt file.wav"""
import sys
import numpy as np
from faster_whisper import WhisperModel
from . import config

_model = None


def _get_model():
    global _model
    if _model is None:
        compute = "int8" if config.WHISPER_DEVICE == "cpu" else "float16"
        _model = WhisperModel(config.WHISPER_MODEL, device=config.WHISPER_DEVICE, compute_type=compute)
    return _model


def transcribe(pcm: bytes, language: str = None) -> str:
    """pcm = raw 16-bit mono 16kHz."""
    lang = language or config.STT_LANGUAGE
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _ = _get_model().transcribe(audio, language=lang, vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()


if __name__ == "__main__":
    import wave
    with wave.open(sys.argv[1], "rb") as w:
        assert w.getframerate() == config.SAMPLE_RATE and w.getnchannels() == 1, "Must be 16kHz mono WAV"
        print(transcribe(w.readframes(w.getnframes())))
