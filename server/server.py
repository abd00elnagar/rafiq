"""WebSocket server. تشغيل:  python -m server.server"""
import asyncio
import json
import websockets
from . import config, stt, tts
from .llm import LLM


async def send_state(ws, state: str):
    await ws.send(json.dumps({"type": "state", "state": state}))


async def run_turn(ws, llm: LLM, pcm: bytes, language: str = "ar"):
    await send_state(ws, "thinking")

    stt_lang = config.get_stt_language(language)
    text = await asyncio.to_thread(stt.transcribe, pcm, stt_lang)
    print(f"[STT ({stt_lang})] {text!r}")
    await ws.send(json.dumps({"type": "transcript", "role": "user", "text": text}))
    if not text:
        await send_state(ws, "idle")
        return

    answer = await asyncio.to_thread(llm.reply, text, language)
    print(f"[LLM ({language})] {answer!r}")
    await ws.send(json.dumps({"type": "transcript", "role": "assistant", "text": answer}))

    await send_state(ws, "speaking")
    voice = config.get_tts_voice(language)
    async for chunk in tts.synth(answer, voice=voice):
        await ws.send(chunk)                      # binary = audio response
    await ws.send(json.dumps({"type": "tts_end"}))
    await send_state(ws, "idle")


async def handler(ws):
    print("[+] client connected")
    current_lang = config.LANGUAGE or "ar"
    llm, buf = LLM(language=current_lang), bytearray()
    try:
        # Inform client about current default language
        await ws.send(json.dumps({"type": "language_changed", "language": current_lang}))
        async for msg in ws:
            if isinstance(msg, bytes):            # binary = microphone audio
                buf.extend(msg)
                continue
            data = json.loads(msg)                # text = JSON commands
            if data["type"] == "set_language":
                current_lang = data.get("language", "ar").lower().strip()
                llm.set_language(current_lang)
                await ws.send(json.dumps({"type": "language_changed", "language": current_lang}))
                print(f"[*] language switched to: {current_lang}")
            elif data["type"] == "start":
                if "language" in data and data["language"]:
                    current_lang = data["language"].lower().strip()
                    llm.set_language(current_lang)
                buf.clear()
                await send_state(ws, "listening")
            elif data["type"] == "end":
                pcm, buf = bytes(buf), bytearray()
                await run_turn(ws, llm, pcm, current_lang)
    except websockets.ConnectionClosed:
        pass
    print("[-] client disconnected")


async def main():
    async with websockets.serve(handler, config.HOST, config.PORT):
        print(f"Server on ws://{config.HOST}:{config.PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
