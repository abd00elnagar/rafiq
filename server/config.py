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

# 3 Voice Profiles (Personas for Rafiq)
VOICE_PROFILES = {
    "v1": {
        "name_ar": "شاكر",
        "name_en": "Guy",
        "ar": os.getenv("TTS_VOICE_V1_AR", "ar-EG-ShakirNeural"),
        "en": os.getenv("TTS_VOICE_V1_EN", "en-US-GuyNeural"),
    },
    "v2": {
        "name_ar": "سلمى",
        "name_en": "Jenny",
        "ar": os.getenv("TTS_VOICE_V2_AR", "ar-EG-SalmaNeural"),
        "en": os.getenv("TTS_VOICE_V2_EN", "en-US-JennyNeural"),
    },
    "v3": {
        "name_ar": "كريم",
        "name_en": "Kareem",
        "ar": os.getenv("TTS_VOICE_V3_AR", "ar-SA-HamedNeural"),
        "en": os.getenv("TTS_VOICE_V3_EN", "en-US-ChristopherNeural"),
    },
}
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "v1")

TTS_VOICES = {
    "ar": VOICE_PROFILES["v1"]["ar"],
    "en": VOICE_PROFILES["v1"]["en"],
}


def get_system_prompt(lang: str = "ar") -> str:
    lang = (lang or "ar").lower().strip()
    if lang == "ar":
        return (
            "You are Rafiq (رفيق), a friendly Egyptian voice assistant. "
            "CRITICAL: The user is speaking to you through an audio microphone transcribed by Egyptian speech recognition. "
            "Tolerate minor phonetic ASR variations or colloquial spelling (e.g. 'عايز/عاوز', 'كدا/كده', 'ازيك/إزاي حضرتك') and deduce their true intent seamlessly.\n"
            "CRITICAL: Your output will be read aloud immediately by an audio synthesizer on an ESP32 speaker. "
            "Strictly follow these phonetic rules for spoken voice:\n"
            "1. Respond ONLY in genuine, warm Egyptian Arabic (اللهجة العامية المصرية القاهرية).\n"
            "2. NEVER output digits or numbers (0-9). ALWAYS spell numbers as Egyptian spoken words (e.g. write 'مية وخمسين' not '150', 'أربعة ونص' not '4:30', 'عشرة' not '10').\n"
            "3. Write words phonetically as pronounced in Cairo: write 'كدا' NOT 'كده', write 'دا' NOT 'ده', write 'عشان' NOT 'علشان'.\n"
            "4. NEVER write English letters or acronyms in Arabic mode. Transliterate them phonetically into Arabic script (e.g. write 'واي فاي' not 'Wi-Fi', 'بي دي إف' not 'PDF', 'أوكي' not 'OK', 'واتساب' not 'WhatsApp').\n"
            "5. Keep your response strictly to one or two short, direct sentences.\n"
            "6. NEVER use markdown, emojis, asterisks (*), hashtags (#), brackets, colons, or bullet points. Use only commas and periods for natural speech pauses."
        )
    else:
        return (
            "You are Rafiq, a friendly voice assistant. "
            "CRITICAL: The user is speaking through a microphone; tolerate minor speech recognition transcription imperfections and understand their intent seamlessly.\n"
            "CRITICAL: Your output will be read aloud immediately by an audio synthesizer on an ESP32 speaker. "
            "Strictly follow these spoken voice rules:\n"
            "1. Respond in natural, warm, conversational English.\n"
            "2. NEVER use digits or symbols (e.g. write 'forty-five' not '45', 'five dollars' not '$5', 'percent' not '%').\n"
            "3. Expand abbreviations into full spoken words (e.g. write 'for example' not 'e.g.').\n"
            "4. Keep your answer strictly to one or two short sentences, suitable to be read aloud.\n"
            "5. NEVER use markdown, emojis, asterisks (*), hashtags (#), brackets, colons, or bullet points. Use only commas and periods for natural breathing pauses."
        )


def get_tts_voice(lang: str = "ar", voice_id: str = "v1") -> str:
    lang = (lang or "ar").lower().strip()
    profile = VOICE_PROFILES.get(voice_id or DEFAULT_VOICE, VOICE_PROFILES["v1"])
    return profile.get(lang, profile.get("ar", "ar-EG-ShakirNeural"))


def get_stt_language(lang: str = "ar") -> str:
    return "ar" if (lang or "ar").lower().strip() == "ar" else "en"


# ---- STT ----
STT_PROVIDER = os.getenv("STT_PROVIDER", "auto").lower().strip()   # auto / groq / local
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")  # whisper-large-v3 or whisper-large-v3-turbo
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")   # base / small / medium / large-v3-turbo
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")   # cpu or cuda
STT_LANGUAGE = os.getenv("STT_LANGUAGE", get_stt_language(LANGUAGE))

# ---- LLM (OpenRouter) ----
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "nvidia/nemotron-3.5-lightning:free")
SYSTEM_PROMPT = get_system_prompt(LANGUAGE)

# ---- TTS ----
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "namaa").lower().strip()
TTS_VOICE = get_tts_voice(LANGUAGE)


