"""Text-to-Speech -> PCM 16kHz mono streaming chunks.
Requires ffmpeg installed on system. Test: python -m server.tts "Hello" (writes out.pcm)"""
import asyncio
import sys
import edge_tts
from . import config


async def synth(text: str, voice: str = None):
    v = voice or config.TTS_VOICE
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-loglevel", "quiet", "-i", "pipe:0",
        "-f", "s16le", "-ar", str(config.SAMPLE_RATE), "-ac", "1", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
    )

    async def feed():
        async for part in edge_tts.Communicate(text, v).stream():
            if part["type"] == "audio":
                proc.stdin.write(part["data"])
                await proc.stdin.drain()
        proc.stdin.close()

    feeder = asyncio.create_task(feed())
    while True:
        data = await proc.stdout.read(config.CHUNK_BYTES)
        if not data:
            break
        yield data
    await feeder
    await proc.wait()


if __name__ == "__main__":
    async def _t():
        with open("out.pcm", "wb") as f:
            async for c in synth(sys.argv[1]):
                f.write(c)
        print("Done: out.pcm (test play: ffplay -f s16le -ar 16000 -ac 1 out.pcm)")
    asyncio.run(_t())
