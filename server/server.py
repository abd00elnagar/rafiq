"""WebSocket server. تشغيل:  python -m server.server"""
import asyncio
import json
import websockets
from . import config, stt, tts
from .llm import LLM


async def send_state(ws, state: str):
    await ws.send(json.dumps({"type": "state", "state": state}))


async def run_turn(ws, llm: LLM, pcm: bytes):
    await send_state(ws, "thinking")

    text = await asyncio.to_thread(stt.transcribe, pcm)
    print(f"[STT] {text!r}")
    await ws.send(json.dumps({"type": "transcript", "role": "user", "text": text}))
    if not text:
        await send_state(ws, "idle")
        return

    answer = await asyncio.to_thread(llm.reply, text)
    print(f"[LLM] {answer!r}")
    await ws.send(json.dumps({"type": "transcript", "role": "assistant", "text": answer}))

    await send_state(ws, "speaking")
    async for chunk in tts.synth(answer):
        await ws.send(chunk)                      # binary = audio response
    await ws.send(json.dumps({"type": "tts_end"}))
    await send_state(ws, "idle")


async def handler(ws):
    print("[+] client connected")
    llm, buf = LLM(), bytearray()
    try:
        async for msg in ws:
            if isinstance(msg, bytes):            # binary = microphone audio
                buf.extend(msg)
                continue
            data = json.loads(msg)                # text = JSON commands
            if data["type"] == "start":
                buf.clear()
                await send_state(ws, "listening")
            elif data["type"] == "end":
                pcm, buf = bytes(buf), bytearray()
                await run_turn(ws, llm, pcm)
    except websockets.ConnectionClosed:
        pass
    print("[-] client disconnected")


async def main():
    async with websockets.serve(handler, config.HOST, config.PORT):
        print(f"Server on ws://{config.HOST}:{config.PORT}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
