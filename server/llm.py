"""LLM via OpenRouter.
Standalone test: python -m server.llm (requires OPENROUTER_API_KEY in .env)
MCP tools will be added here later."""
from openai import OpenAI
from . import config


class LLM:
    def __init__(self):
        self.client = OpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY or "missing-key",
            default_headers={
                "HTTP-Referer": "https://github.com/rafiq-assistant",
                "X-Title": "Rafiq Voice Assistant",
            },
        )
        self.history = []          # Each connection maintains its own conversation history

    def reply(self, user_text: str) -> str:
        if not config.OPENROUTER_API_KEY or config.OPENROUTER_API_KEY.strip() == "your_openrouter_api_key_here":
            raise ValueError(
                "OPENROUTER_API_KEY is not set! Please set your key in the .env file."
            )

        self.history.append({"role": "user", "content": user_text})
        messages = [{"role": "system", "content": config.SYSTEM_PROMPT}] + self.history[-20:]
        
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
        text = (msg.content or getattr(msg, "reasoning", "") or "").strip()
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

