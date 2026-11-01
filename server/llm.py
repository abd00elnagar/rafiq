"""LLM via OpenRouter.
Standalone test: python -m server.llm (requires OPENROUTER_API_KEY in .env)
MCP tools will be added here later."""
import re
from openai import OpenAI
from . import config


def clean_text(text: str, lang: str = "ar") -> str:
    """Remove rogue foreign scripts and markdown formatting."""
    if not text:
        return ""
    # Strip CJK (Chinese, Japanese, Korean), Hebrew, and Cyrillic glyphs
    text = re.sub(r'[\u4e00-\u9fff\u3040-\u30ff\u3400-\u4dbf\u0590-\u05ff\u0400-\u04ff]', '', text)
    # Strip markdown symbols
    text = re.sub(r'[*_#`~\[\]]', '', text)
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

