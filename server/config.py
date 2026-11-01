import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Ensure ffmpeg in user PATH is discovered on Windows even without terminal restart
import shutil
if os.name == "nt" and not shutil.which("ffmpeg"):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as _k:
            _reg_path, _ = winreg.QueryValueEx(_k, "Path")
            os.environ["PATH"] = _reg_path + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

# ---- Audio contract (must match on ESP32 and server) ----
SAMPLE_RATE = 16000      # Hz
CHUNK_MS = 40            # Audio packet size in milliseconds
CHUNK_BYTES = SAMPLE_RATE * CHUNK_MS // 1000 * 2   # 16-bit mono = 2 bytes/sample

# ---- Server ----
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8765"))

# ---- Language Configuration ----
# Supported options: 'ar' (Arabic) or 'en' (English)
LANGUAGE = os.getenv("LANGUAGE", "ar").lower().strip()

TTS_VOICES = {
    "ar": os.getenv("TTS_VOICE", "ar-EG-SalmaNeural"),
    "en": "en-US-JennyNeural",
}


def get_system_prompt(lang: str = "ar") -> str:
    lang = (lang or "ar").lower().strip()
    if lang == "ar":
        return (
            "You are Rafiq (رفيق), a friendly voice assistant. "
            "You MUST respond ONLY in natural Egyptian Arabic (اللهجة العامية المصرية). "
            "STRICT RULES: "
            "1. NEVER output Chinese, Japanese, Hebrew, or any foreign scripts. "
            "2. Keep your answer strictly to one or two short sentences, suitable to be read aloud. "
            "3. Do NOT use markdown, emojis, asterisks, bullet points, or symbols."
        )
    else:
        return (
            "You are Rafiq, a friendly voice assistant. "
            "You MUST respond in natural English. "
            "STRICT RULES: "
            "1. Keep your answer strictly to one or two short sentences, suitable to be read aloud. "
            "2. Do NOT use markdown, emojis, asterisks, bullet points, or symbols."
        )


def get_tts_voice(lang: str = "ar") -> str:
    return TTS_VOICES.get((lang or "ar").lower().strip(), TTS_VOICES["ar"])


def get_stt_language(lang: str = "ar") -> str:
    return "ar" if (lang or "ar").lower().strip() == "ar" else "en"


# ---- STT ----
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")   # base / small / medium
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")   # cpu or cuda
STT_LANGUAGE = os.getenv("STT_LANGUAGE", get_stt_language(LANGUAGE))

# ---- LLM (OpenRouter) ----
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "nvidia/nemotron-3.5-lightning:free")
SYSTEM_PROMPT = get_system_prompt(LANGUAGE)

# ---- TTS ----
TTS_VOICE = get_tts_voice(LANGUAGE)


