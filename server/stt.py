"""Production-grade Speech-to-Text with Egyptian Arabic conditioning and audio normalization.
Supports:
- Local faster-whisper (CPU or CUDA) with dialect conditioning & anti-hallucination VAD
- Groq Cloud Whisper (Whisper Large-V3 / Turbo) for ultra-low latency & 99%+ accuracy

Standalone test: python -m server.stt audio_samples/ar_01_colloquial_salma.wav
"""
import io
import os
import sys
import wave
import numpy as np
from . import config

# Ensure terminal stdout handles UTF-8 Arabic cleanly on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

_model = None

# Contextual prompts biasing Whisper toward conversational Egyptian Arabic or English
EGYPTIAN_ARABIC_PROMPT = (
    "محادثة بالعامية المصرية: السلام عليكم، إزاي حضرتك، عامل إيه، تمام، ماشي، دلوقتي، "
    "عايز، رفيق، علشان، روق كده، وصلي على النبي، مية وخمسين جنيه، كويس، إيه الأخبار، "
    "ابعتلي، شكراً، مع السلامة."
)

ENGLISH_PROMPT = (
    "Conversational voice assistant dialogue: Rafiq, hello, how are you doing, "
    "could you help me with this, thank you, goodbye."
)


def _get_model():
    """Lazily load faster-whisper model."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        compute = "int8" if config.WHISPER_DEVICE == "cpu" else "float16"
        print(f"[STT] Loading local faster-whisper ({config.WHISPER_MODEL}) on {config.WHISPER_DEVICE} ({compute})...")
        _model = WhisperModel(config.WHISPER_MODEL, device=config.WHISPER_DEVICE, compute_type=compute)
    return _model


def normalize_audio(audio: np.ndarray) -> np.ndarray:
    """Normalize volume and remove DC offset so quiet mic audio or slight offset is not missed."""
    if len(audio) == 0:
        return audio
    # Remove DC offset (center waveform around 0.0)
    audio = audio - np.mean(audio)
    peak = np.max(np.abs(audio))
    if peak > 0.005:  # Avoid amplifying pure background silence/noise floor
        audio = audio * (0.95 / peak)
    return audio


def transcribe_local(pcm: bytes, language: str = "ar") -> str:
    """Local faster-whisper with dialect prompt and anti-hallucination settings."""
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    audio = normalize_audio(audio)

    prompt = EGYPTIAN_ARABIC_PROMPT if language == "ar" else ENGLISH_PROMPT

    segments, _ = _get_model().transcribe(
        audio,
        language=language,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400, speech_pad_ms=250),
        initial_prompt=prompt,
        beam_size=5,
        best_of=5,
        temperature=(0.0, 0.2),
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        compression_ratio_threshold=2.4,
    )
    return " ".join(s.text.strip() for s in segments).strip()


def transcribe_groq(pcm: bytes, language: str = "ar") -> str:
    """Ultra-fast cloud Whisper Large-V3 (150-300ms latency) via Groq."""
    from openai import OpenAI

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=config.GROQ_API_KEY,
    )

    # Wrap raw PCM into a WAV file buffer in memory
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(config.SAMPLE_RATE)
        wf.writeframes(pcm)
    buf.seek(0)
    buf.name = "audio.wav"

    prompt = EGYPTIAN_ARABIC_PROMPT if language == "ar" else ENGLISH_PROMPT

    resp = client.audio.transcriptions.create(
        model=config.GROQ_STT_MODEL,
        file=buf,
        language=language,
        prompt=prompt,
        temperature=0.0,
    )
    return resp.text.strip()


def transcribe(pcm: bytes, language: str = None) -> str:
    """pcm = raw 16-bit mono 16kHz audio."""
    if not pcm or len(pcm) < config.CHUNK_BYTES:
        return ""

    lang = config.get_stt_language(language)

    # Use Groq Cloud if configured and API key is present
    should_use_groq = (
        config.STT_PROVIDER in ("groq", "auto")
        and bool(config.GROQ_API_KEY)
    )

    if should_use_groq:
        try:
            return transcribe_groq(pcm, lang)
        except Exception as e:
            print(f"[STT] Groq Cloud failed ({e}), falling back to local faster-whisper...")

    return transcribe_local(pcm, lang)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m server.stt <path_to_16khz_mono_wav> [lang]")
        sys.exit(1)

    wav_file = sys.argv[1]
    target_lang = sys.argv[2] if len(sys.argv) > 2 else "ar"

    with wave.open(wav_file, "rb") as w:
        assert w.getframerate() == config.SAMPLE_RATE, f"Sample rate must be {config.SAMPLE_RATE}Hz"
        assert w.getnchannels() == 1, "Must be mono channel"
        assert w.getsampwidth() == 2, "Must be 16-bit PCM"
        raw_pcm = w.readframes(w.getnframes())

    result = transcribe(raw_pcm, target_lang)
    print(f"\n[STT ({target_lang}) Result]:\n{result}")
