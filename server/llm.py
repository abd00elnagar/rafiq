"""LLM via OpenRouter.
Standalone test: python -m server.llm (requires OPENROUTER_API_KEY in .env)
MCP tools will be added here later."""
import re
from openai import OpenAI
from . import config


AR_NUM_MAP = {
    "0": "صفر", "1": "واحد", "2": "اتنين", "3": "تلاتة", "4": "أربعة",
    "5": "خمسة", "6": "ستة", "7": "سبعة", "8": "تمانية", "9": "تسعة",
    "10": "عشرة", "11": "حداشر", "12": "اتناشر", "13": "تلاتاشر", "14": "اربعتاشر",
    "15": "خمستاشر", "16": "ستاشر", "17": "سبعتاشر", "18": "تمنتاشر", "19": "تسعتاشر",
    "20": "عشرين", "25": "خمسة وعشرين", "30": "تلاتين", "40": "أربعين", "50": "خمسين",
    "60": "ستين", "70": "سبعين", "80": "تمانين", "90": "تسعين",
    "100": "مية", "150": "مية وخمسين", "200": "ميتين", "500": "خمسمية", "1000": "ألف"
}

AR_COLLOQUIAL_MAP = {
    r"\bكده\b": "كدا",
    r"\bده\b": "دا",
    r"\bعلشان\b": "عشان",
    r"\bمفيش\b": "مافيش",
}

TECH_TERMS_MAP = {
    r"\bwi-?fi\b": "واي فاي",
    r"\bpdf\b": "بي دي إف",
    r"\bok(?:ay)?\b": "أوكي",
    r"\bwhatsapp\b": "واتساب",
    r"\bapp\b": "أبلكيشن",
    r"\bmeeting\b": "ميتنج",
    r"\blocation\b": "لوكيشن",
    r"\blink\b": "لينك",
    r"\bgps\b": "جي بي إس",
    r"\busb\b": "يو إس بي",
    r"\bai\b": "ذكاء اصطناعي",
}

EN_DIGITS_MAP = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten"
}


def clean_text(text: str, lang: str = "ar") -> str:
    """Deterministic Voice Shield: Sanitize and normalize text for flawless TTS synthesis."""
    if not text:
        return ""
    lang = (lang or "ar").lower().strip()

    # 1. Strip emojis and pictographs
    text = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u200d\ufe0f]', '', text)

    # 2. Strip foreign non-Arabic/non-Latin scripts (CJK, Hebrew, Cyrillic)
    text = re.sub(r'[\u4e00-\u9fff\u3040-\u30ff\u3400-\u4dbf\u0590-\u05ff\u0400-\u04ff]', '', text)

    # 3. Strip markdown syntax, brackets, quotes, dashes and colons (preserve contractions like didn't)
    text = re.sub(r'[*_#`~\[\]{}()<>\\/|^+=–—\":]', ' ', text)
    text = re.sub(r"(?<![a-zA-Z])'|'(?![a-zA-Z])", ' ', text)

    if lang == "ar":
        # 4a. Translate Eastern Arabic numerals (٠-٩) to standard digits
        eastern_digits = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        text = text.translate(eastern_digits)

        # 4b. Symbols to spoken Arabic
        text = text.replace("%", " في المية ").replace("$", " دولار ").replace("£", " جنيه ")

        # 4c. Egyptian colloquial phonetics
        for pat, repl in AR_COLLOQUIAL_MAP.items():
            text = re.sub(pat, repl, text)

        # 4d. Transliterate English tech acronyms into Arabic script
        for pat, repl in TECH_TERMS_MAP.items():
            text = re.sub(pat, repl, text, flags=re.IGNORECASE)

        # 4e. Remove any remaining raw Latin letters/words in Arabic mode to prevent TTS corruption
        text = re.sub(r'[a-zA-Z]+', '', text)

        # 4f. Digits to Egyptian spoken words
        for num, word in sorted(AR_NUM_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            text = re.sub(rf'\b{num}\b', f' {word} ', text)
        for d, w in [("0", "صفر"), ("1", "واحد"), ("2", "اتنين"), ("3", "تلاتة"), ("4", "أربعة"),
                    ("5", "خمسة"), ("6", "ستة"), ("7", "سبعة"), ("8", "تمانية"), ("9", "تسعة")]:
            text = text.replace(d, f' {w} ')
    else:
        # 5. English symbol and currency expansions
        text = re.sub(r'\$(\d+)', r'\1 dollars', text)
        text = text.replace("$", " dollars ")
        text = re.sub(r'(\d+)%', r'\1 percent', text)
        text = text.replace("%", " percent ").replace("&", " and ")
        for d, w in EN_DIGITS_MAP.items():
            text = re.sub(rf'\b{d}\b', f' {w} ', text)

    # 6. Normalize punctuation (collapse multiple punctuation into natural speech pauses)
    text = re.sub(r'\?+', '?', text)
    text = re.sub(r'!+', '!', text)
    text = re.sub(r'\.+', '.', text)
    text = re.sub(r',+', ',', text)

    # 7. Collapse spaces
    return " ".join(text.split()).strip()


class LLM:
    def __init__(self, language: str = None):
        self.language = (language or config.LANGUAGE or "ar").lower().strip()
        self.client = OpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY or "missing-key",
            default_headers={
                "HTTP-Referer": "https://github.com/rafiq-assistant",
                "X-Title": "Rafiq Voice Assistant",
            },
        )
        self.history = []          # Each connection maintains its own conversation history

    def set_language(self, language: str):
        self.language = (language or "ar").lower().strip()

    def reply(self, user_text: str, language: str = None) -> str:
        lang = (language or self.language or "ar").lower().strip()
        if not config.OPENROUTER_API_KEY or config.OPENROUTER_API_KEY.strip() == "your_openrouter_api_key_here":
            raise ValueError(
                "OPENROUTER_API_KEY is not set! Please set your key in the .env file."
            )

        self.history.append({"role": "user", "content": user_text})
        system_prompt = config.get_system_prompt(lang)
        messages = [{"role": "system", "content": system_prompt}] + self.history[-20:]
        
        create_kwargs = {
            "model": config.LLM_MODEL,
            "max_tokens": 300,
            "messages": messages,
        }
        # Disable excessive reasoning tokens for reasoning models so responses remain fast and direct
        if ":free" in config.LLM_MODEL or "nemotron" in config.LLM_MODEL.lower():
            create_kwargs["extra_body"] = {"reasoning": {"max_tokens": 0}}

        resp = self.client.chat.completions.create(**create_kwargs)
        msg = resp.choices[0].message
        raw_text = (msg.content or getattr(msg, "reasoning", "") or "").strip()
        text = clean_text(raw_text, lang)
        self.history.append({"role": "assistant", "content": text})
        return text


if __name__ == "__main__":
    llm = LLM()
    print("=== LLM Test (OpenRouter) ===")
    print(f"Model: {config.LLM_MODEL}")
    print("Type your message and press Enter. Press Ctrl+C to exit.\n")
    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            answer = llm.reply(user_input)
            print(f"Rafiq: {answer}\n")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break
        except Exception as e:
            print(f"Error: {e}\n")

