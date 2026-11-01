"""Simulates ESP32 on PC: mic -> server -> speaker.
Run: python sim_client/sim_client.py ws://localhost:8765
Press Enter to start speaking, press Enter again to stop."""
import asyncio
import json
import sys
import sounddevice as sd
import websockets

SR, CHUNK_MS = 16000, 40
URL = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8765"


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


async def record_and_send(ws):
    loop, q = asyncio.get_running_loop(), asyncio.Queue()

    def cb(indata, frames, t, status):
        loop.call_soon_threadsafe(q.put_nowait, bytes(indata))

    await ws.send(json.dumps({"type": "start"}))
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
    async with websockets.connect(URL, max_size=None) as ws:
        recv = asyncio.create_task(receiver(ws, speaker))
        while True:
            await asyncio.to_thread(input, "\nPress Enter to speak: ")
            await record_and_send(ws)


if __name__ == "__main__":
    asyncio.run(main())
