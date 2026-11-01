"""Simulates ESP32 on PC: mic -> server -> speaker.
Run: python sim_client/sim_client.py [URL] [LANGUAGE]
Example: python sim_client/sim_client.py ws://localhost:8765 ar
Press Enter to speak, or type 'ar'/'en' to switch language."""
import asyncio
import json
import sys
import sounddevice as sd
import websockets

SR, CHUNK_MS = 16000, 40
URL = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith("ws") else "ws://localhost:8765"
DEFAULT_LANG = sys.argv[2] if len(sys.argv) > 2 else (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("ws") else "ar")


async def receiver(ws, speaker):
    async for msg in ws:
        if isinstance(msg, bytes):
            await asyncio.to_thread(speaker.write, msg)
        else:
            d = json.loads(msg)
            if d["type"] == "state":
                print(f"  [state] {d['state']}")
            elif d["type"] == "transcript":
                print(f"  [{d['role']}] {d['text']}")
            elif d["type"] == "language_changed":
                print(f"  [language set to] {d['language']}")


async def record_and_send(ws, lang: str):
    loop, q = asyncio.get_running_loop(), asyncio.Queue()

    def cb(indata, frames, t, status):
        loop.call_soon_threadsafe(q.put_nowait, bytes(indata))

    await ws.send(json.dumps({"type": "start", "language": lang}))
    stop = asyncio.create_task(asyncio.to_thread(input, "  ...Recording. Press Enter to stop\n"))
    with sd.RawInputStream(samplerate=SR, channels=1, dtype="int16",
                           blocksize=SR * CHUNK_MS // 1000, callback=cb):
        while not stop.done():
            try:
                await ws.send(await asyncio.wait_for(q.get(), 0.1))
            except asyncio.TimeoutError:
                pass
    await ws.send(json.dumps({"type": "end"}))


async def main():
    speaker = sd.RawOutputStream(samplerate=SR, channels=1, dtype="int16")
    speaker.start()
    current_lang = DEFAULT_LANG.lower().strip()

    print(f"Connecting to {URL} ...")
    async with websockets.connect(URL, max_size=None) as ws:
        recv = asyncio.create_task(receiver(ws, speaker))
        # Set initial language on server
        await ws.send(json.dumps({"type": "set_language", "language": current_lang}))
        print(f"\n=== Rafiq Voice Assistant Client ===")
        print(f"Active Language: {current_lang.upper()} ('ar' = Arabic | 'en' = English)")
        print(f"Controls: Press Enter to speak | Type 'ar' or 'en' then Enter to switch language\n")

        while True:
            cmd = (await asyncio.to_thread(input, f"\n[{current_lang.upper()}] Press Enter to speak (or type 'ar'/'en'): ")).strip().lower()
            if cmd in ("ar", "arabic", "عربي"):
                current_lang = "ar"
                await ws.send(json.dumps({"type": "set_language", "language": "ar"}))
                print(">> Switched language to: Arabic (العربية)")
            elif cmd in ("en", "english", "انجليزي"):
                current_lang = "en"
                await ws.send(json.dumps({"type": "set_language", "language": "en"}))
                print(">> Switched language to: English")
            else:
                await record_and_send(ws, current_lang)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nClient stopped.")
