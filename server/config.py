import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ---- Audio contract (must match on ESP32 and server) ----
SAMPLE_RATE = 16000      # Hz
CHUNK_MS = 40            # Audio packet size in milliseconds
CHUNK_BYTES = SAMPLE_RATE * CHUNK_MS // 1000 * 2   # 16-bit mono = 2 bytes/sample

# ---- Server ----
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8765"))

# ---- STT ----
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")   # base / small / medium
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")   # cpu or cuda
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "ar")        # None = auto-detect

# ---- LLM (OpenRouter) ----
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "anthropic/claude-3.5-sonnet")
SYSTEM_PROMPT = (
    "You are a voice assistant like Alexa. Your responses must be short (one or two sentences) "
    "without markdown, symbols, or lists, because the response will be read aloud. "
    "Respond in the same language as the user, and in Egyptian Arabic if spoken to in it."
)

# ---- TTS ----
TTS_VOICE = os.getenv("TTS_VOICE", "ar-EG-SalmaNeural")   # or ar-EG-ShakirNeural


