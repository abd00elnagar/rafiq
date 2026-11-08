"""WebSocket server. تشغيل:  python -m server.server"""
import asyncio
import json
import websockets
from . import config, stt, tts
from .llm import LLM


async def send_state(ws, state: str):
    await ws.send(json.dumps({"type": "state", "state": state}))


async def run_turn(ws, llm: LLM, pcm: bytes, language: str = "ar", voice: str = "v1"):
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
    tts_voice = config.get_tts_voice(language, voice_id=voice)
    async for chunk in tts.synth(answer, voice=tts_voice):
        await ws.send(chunk)                      # binary = audio response
    await ws.send(json.dumps({"type": "tts_end"}))
    await send_state(ws, "idle")


async def handler(ws):
    print("[+] client connected")
    current_lang = config.LANGUAGE or "ar"
    current_voice = getattr(config, "DEFAULT_VOICE", "v1")
    llm, buf = LLM(language=current_lang), bytearray()
    try:
        # Inform client about current default language and voice
        await ws.send(json.dumps({
            "type": "init",
            "language": current_lang,
            "voice": current_voice,
        }))
        await ws.send(json.dumps({"type": "language_changed", "language": current_lang}))
        await ws.send(json.dumps({"type": "voice_changed", "voice": current_voice}))
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
            elif data["type"] == "set_voice":
                current_voice = data.get("voice", "v1").lower().strip()
                await ws.send(json.dumps({"type": "voice_changed", "voice": current_voice}))
                print(f"[*] voice switched to: {current_voice}")
            elif data["type"] == "start":
                if "language" in data and data["language"]:
                    current_lang = data["language"].lower().strip()
                    llm.set_language(current_lang)
                if "voice" in data and data["voice"]:
                    current_voice = data["voice"].lower().strip()
                buf.clear()
                await send_state(ws, "listening")
            elif data["type"] == "end":
                pcm, buf = bytes(buf), bytearray()
                await run_turn(ws, llm, pcm, current_lang, current_voice)
            elif data["type"] == "text":
                user_text = data.get("text", "").strip()
                if user_text:
                    await ws.send(json.dumps({"type": "transcript", "role": "user", "text": user_text}))
                    await send_state(ws, "thinking")
                    answer = await asyncio.to_thread(llm.reply, user_text, current_lang)
                    print(f"[LLM ({current_lang})] {answer!r}")
                    await ws.send(json.dumps({"type": "transcript", "role": "assistant", "text": answer}))
                    await send_state(ws, "speaking")
                    tts_voice = config.get_tts_voice(current_lang, voice_id=current_voice)
                    async for chunk in tts.synth(answer, voice=tts_voice):
                        await ws.send(chunk)
                    await ws.send(json.dumps({"type": "tts_end"}))
                    await send_state(ws, "idle")
    except websockets.ConnectionClosed:
        pass
    print("[-] client disconnected")


async def main():
    async with websockets.serve(handler, config.HOST, config.PORT):
        print(f"Server on ws://{config.HOST}:{config.PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
