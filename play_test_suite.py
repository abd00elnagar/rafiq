"""Interactive & Automated TTS Test Suite for Rafiq.
Plays high-quality test sentences directly on your speakers and saves .wav files to 'audio_samples/'.

Usage:
  python play_test_suite.py              # Plays curated Egyptian Arabic & English tests
  python play_test_suite.py --ar         # Plays Egyptian Arabic tests only (NAMAA)
  python play_test_suite.py --en         # Plays English tests only (Christopher)
  python play_test_suite.py --say "نص للتجربة"
"""

import argparse
import asyncio
import os
import subprocess
import sys
import wave
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
import sounddevice as sd
from server import config, tts
from server.llm import clean_text

OUTPUT_DIR = Path(__file__).parent / "audio_samples"
OUTPUT_DIR.mkdir(exist_ok=True)

# Curated test suite designed to demonstrate normalized phonetic delivery
TEST_CASES = [
    # --- Egyptian Arabic Tests ---
    {
        "id": "ar_01_colloquial_namaa",
        "lang": "ar",
        "voice": "ar-EG-SalmaNeural",
        "label": "Egyptian Arabic (Casual / NAMAA)",
        "raw_text": "يا سيدي ولا يهمك، كل مشكلة وليها حل، بس انت روق كده وصلي على النبي.",
    },
    {
        "id": "ar_02_question_namaa",
        "lang": "ar",
        "voice": "ar-EG-SalmaNeural",
        "label": "Question & Intonation (NAMAA)",
        "raw_text": "أنت بجد مش فاكرني؟! إزاي نسيت اللي حصل إمبارح بالليل؟!",
    },
    {
        "id": "ar_03_numbers_namaa",
        "lang": "ar",
        "voice": "ar-EG-SalmaNeural",
        "label": "Numbers, Currency & Time (NAMAA)",
        "raw_text": "الساعة دلوقتي 4:30 العصر، ومعايا في المحفظة 150 جنيه وده ممتاز.",
    },
    {
        "id": "ar_04_loanwords_namaa",
        "lang": "ar",
        "voice": "ar-EG-SalmaNeural",
        "label": "Tech & English Loanwords (NAMAA)",
        "raw_text": "ابعتلي اللوكيشن على WhatsApp علشان أظبط الـ WiFi وأعدي عليك.",
    },

    # --- English Tests ---
    {
        "id": "en_01_conversational",
        "lang": "en",
        "voice": "en-US-ChristopherNeural",
        "label": "Conversational Natural (Christopher)",
        "raw_text": "Hey there! I didn't quite catch that, could you run that by me one more time?",
    },
    {
        "id": "en_02_numbers_acronyms",
        "lang": "en",
        "voice": "en-US-ChristopherNeural",
        "label": "Numbers & Currency (Christopher)",
        "raw_text": "The total is $50 with a 15% discount for 3 items & free shipping!",
    },
]


def save_wav(filepath: Path, raw_pcm: bytes, sample_rate: int = 16000):
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_pcm)


def play_audio(raw_pcm: bytes, sample_rate: int = 16000):
    samples = np.frombuffer(raw_pcm, dtype=np.int16)
    sd.play(samples, samplerate=sample_rate)
    sd.wait()


async def run_single(raw_text: str, voice: str, lang: str = "ar", label: str = "Custom", save_name: str = "custom", play: bool = True):
    # Pass through the deterministic shield
    clean = clean_text(raw_text, lang)

    print(f"\n==================================================")
    print(f"[*] Playing:  {label}")
    print(f"[*] Raw Text: \"{raw_text}\"")
    print(f"[✓] Cleaned:  \"{clean}\"")
    print(f"==================================================")

    # Synthesize using the server's streaming pipeline
    pcm_buffer = bytearray()
    async for chunk in tts.synth(clean, voice=voice):
        pcm_buffer.extend(chunk)

    raw_pcm = bytes(pcm_buffer)
    wav_path = OUTPUT_DIR / f"{save_name}.wav"
    save_wav(wav_path, raw_pcm)
    print(f"[+] Saved to: audio_samples/{wav_path.name}")

    if play:
        print("[>] Speaking through your speakers now...")
        await asyncio.to_thread(play_audio, raw_pcm)
        print("[✓] Done speaking.")


async def main():
    parser = argparse.ArgumentParser(description="Test Rafiq TTS with audio playback")
    parser.add_argument("--ar", action="store_true", help="Play Arabic test cases only")
    parser.add_argument("--en", action="store_true", help="Play English test cases only")
    parser.add_argument("--say", type=str, default="", help="Say a custom phrase")
    parser.add_argument("--lang", type=str, default="ar", help="Language for custom phrase ('ar' or 'en')")
    parser.add_argument("--voice", type=str, default="", help="Custom voice override")
    parser.add_argument("--no-play", action="store_true", help="Do not play audio, only save files")
    args = parser.parse_args()

    if args.say:
        voice = args.voice or config.get_tts_voice(args.lang)
        await run_single(args.say, voice, lang=args.lang, label="Custom Input", save_name="custom_test", play=not args.no_play)
        return

    selected = TEST_CASES
    if args.ar:
        selected = [c for c in TEST_CASES if c["lang"] == "ar"]
    elif args.en:
        selected = [c for c in TEST_CASES if c["lang"] == "en"]

    print(f"\nStarting Rafiq TTS Benchmark ({len(selected)} samples)...")
    print(f"Audio files are saved in: {OUTPUT_DIR}\n")

    for i, test in enumerate(selected, 1):
        print(f"\n[{i}/{len(selected)}]")
        await run_single(
            raw_text=test["raw_text"],
            voice=test["voice"],
            lang=test["lang"],
            label=test["label"],
            save_name=test["id"],
            play=not args.no_play,
        )
        if not args.no_play and i < len(selected):
            await asyncio.sleep(0.5)

    print("\n[✓] All test cases completed!")


if __name__ == "__main__":
    asyncio.run(main())
