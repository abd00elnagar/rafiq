"""Text-to-Speech -> PCM 16kHz mono streaming chunks.
Supports:
- NAMAA (Egyptian Dialect AI model: omarelshehy/NAMAA-Egyptian-Voice)
- Edge-TTS (Microsoft Neural voices) as fallback/English provider.
Requires ffmpeg installed on system. Test: python -m server.tts "أهلاً يا رفيق" (writes out.pcm)"""
import asyncio
import os
import sys
import edge_tts
from . import config

_namaa_client = None


def _get_namaa_client():
    global _namaa_client
    if _namaa_client is None:
        from gradio_client import Client
        _namaa_client = Client("omarelshehy/NAMAA-Egyptian-Voice")
    return _namaa_client


async def _synth_namaa(text: str):
    """Synthesize Egyptian Arabic speech using the NAMAA model."""
    client = await asyncio.to_thread(_get_namaa_client)
    res_wav = await asyncio.to_thread(
        client.predict,
        text_input=text,
        audio_prompt_path_input=None,
        exaggeration_input=0.5,
        temperature_input=0.8,
        seed_num_input=0,
        cfgw_input=0.5,
        api_name="/generate_tts_audio",
    )

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-loglevel", "quiet", "-i", res_wav,
        "-f", "s16le", "-ar", str(config.SAMPLE_RATE), "-ac", "1", "pipe:1",
        stdout=asyncio.subprocess.PIPE,
    )
    while True:
        data = await proc.stdout.read(config.CHUNK_BYTES)
        if not data:
            break
        yield data
    await proc.wait()


async def _synth_edge(text: str, voice: str):
    """Synthesize speech using Edge-TTS."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-loglevel", "quiet", "-i", "pipe:0",
        "-f", "s16le", "-ar", str(config.SAMPLE_RATE), "-ac", "1", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
    )

    async def feed():
        async for part in edge_tts.Communicate(text, voice).stream():
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


async def synth(text: str, voice: str = None):
    v = voice or config.TTS_VOICE
    use_namaa = (
        getattr(config, "TTS_PROVIDER", "namaa") == "namaa"
        and ("ar" in (v or "").lower() or config.LANGUAGE == "ar")
    )

    if use_namaa:
        try:
            print("[TTS] Synthesizing Egyptian speech with NAMAA model...")
            async for chunk in _synth_namaa(text):
                yield chunk
            return
        except Exception as e:
            print(f"[TTS] NAMAA model error ({e}), falling back to Edge-TTS...")

    # Fallback or English voice
    async for chunk in _synth_edge(text, v):
        yield chunk


if __name__ == "__main__":
    async def _t():
        with open("out.pcm", "wb") as f:
            async for c in synth(sys.argv[1] if len(sys.argv) > 1 else "أهلاً بيك يا فندم"):
                f.write(c)
        print("Done: out.pcm (test play: ffplay -f s16le -ar 16000 -ac 1 out.pcm)")
    asyncio.run(_t())
