import asyncio
import os
from pathlib import Path
from datetime import datetime
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

from dotenv import load_dotenv
from livekit import rtc, api


# ==========================================
# 1. CONFIGURATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

ENV_PATH = (
    BASE_DIR.parent
    / "python_backend"
    / ".env"
)

load_dotenv(ENV_PATH, override=True)

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
API_KEY = os.getenv("LIVEKIT_API_KEY", "")
API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")


def validate_credentials():
    if not all([LIVEKIT_URL, API_KEY, API_SECRET]):
        raise ValueError("Missing LiveKit credentials in .env")


ROOM_NAME = "esp32-test-room"
IDENTITY = "python-esp32-simulator"

SAMPLE_RATE = 48000
CHANNELS = 1
FRAME_MS = 20

SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000


# ==========================================
# 2. RECORDING DIRECTORIES
# ==========================================

RECORDINGS_DIR = BASE_DIR / "recordings"

MIC_DIR = RECORDINGS_DIR / "microphone"
AGENT_DIR = RECORDINGS_DIR / "agent"

MIC_DIR.mkdir(parents=True, exist_ok=True)
AGENT_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================
# 3. AUDIO SAVING FUNCTION
# ==========================================

def save_audio(audio_data, folder, prefix, sample_rate=SAMPLE_RATE):

    if len(audio_data) == 0:
        print("No audio data to save.")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    filename = f"{prefix}_{timestamp}.wav"

    filepath = folder / filename

    audio_data = np.asarray(audio_data, dtype=np.int16)

    sf.write(
        str(filepath),
        audio_data,
        sample_rate,
        subtype="PCM_16",
    )

    print(f"Audio saved: {filepath}")

    return filepath


# ==========================================
# 4. LIVEKIT TOKEN
# ==========================================

def create_token():
    validate_credentials()

    token = (
        api.AccessToken(API_KEY, API_SECRET)
        .with_identity(IDENTITY)
        .with_name("ESP32 Simulator")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=ROOM_NAME,
            )
        )
    )

    return token.to_jwt()


# ==========================================
# 5. MAIN SIMULATOR
# ==========================================

async def main():
    validate_credentials()

    loop = asyncio.get_running_loop()

    room = rtc.Room()

    # Separate recording buffers
    mic_buffer = []
    agent_buffer = []

    # Protect recording buffers
    mic_lock = threading.Lock()
    agent_lock = threading.Lock()

    print("Starting ESP32 simulator...")

    # ======================================
    # 6. MICROPHONE AUDIO SOURCE
    # ======================================

    audio_source = rtc.AudioSource(
        sample_rate=SAMPLE_RATE,
        num_channels=CHANNELS,
    )

    audio_track = rtc.LocalAudioTrack.create_audio_track(
        "esp32-microphone",
        audio_source,
    )

    # ======================================
    # 7. RECEIVE AGENT AUDIO
    # ======================================

    async def play_audio(track):

        print("Agent audio received!")

        audio_stream = rtc.AudioStream(
            track=track,
            sample_rate=SAMPLE_RATE,
            num_channels=CHANNELS,
        )

        try:

            with sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
            ) as speaker:

                async for event in audio_stream:

                    frame = event.frame

                    audio_data = np.frombuffer(
                        frame.data,
                        dtype=np.int16,
                    ).copy()

                    # Save agent audio
                    with agent_lock:
                        agent_buffer.append(audio_data)

                    # Play agent audio
                    speaker.write(audio_data)

        finally:
            await audio_stream.aclose()

    # ======================================
    # 8. LIVEKIT TRACK SUBSCRIPTION
    # ======================================

    @room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant):

        if track.kind == rtc.TrackKind.KIND_AUDIO:

            print(
                f"Subscribed to agent: {participant.identity}"
            )

            asyncio.create_task(
                play_audio(track)
            )

    # ======================================
    # 9. CONNECT TO LIVEKIT
    # ======================================

    print("Connecting to LiveKit...")

    await room.connect(
        LIVEKIT_URL,
        create_token(),
    )

    print("Connected successfully!")

    # ======================================
    # 10. PUBLISH MICROPHONE
    # ======================================

    await room.local_participant.publish_track(
        audio_track
    )

    print("Microphone published!")

    # ======================================
    # 11. MICROPHONE CALLBACK
    # ======================================

    def microphone_callback(
        indata,
        frames,
        time_info,
        status,
    ):

        if status:
            print("Microphone warning:", status)

        pcm = np.asarray(
            indata[:, 0],
            dtype=np.int16,
        ).copy()

        # Save microphone samples
        with mic_lock:
            mic_buffer.append(pcm)

        frame = rtc.AudioFrame(
            data=pcm.tobytes(),
            sample_rate=SAMPLE_RATE,
            num_channels=CHANNELS,
            samples_per_channel=len(pcm),
        )

        asyncio.run_coroutine_threadsafe(
            audio_source.capture_frame(frame),
            loop,
        )

    # ======================================
    # 12. START MICROPHONE
    # ======================================

    print("--------------------------------")
    print("ESP32 SIMULATOR STARTED")
    print("Speak into your microphone")
    print("Press CTRL+C to stop")
    print("--------------------------------")

    try:

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=SAMPLES_PER_FRAME,
            callback=microphone_callback,
        ):

            await asyncio.Future()

    finally:

        print("Saving recordings...")

        # Save microphone recording
        with mic_lock:
            mic_data = (
                np.concatenate(mic_buffer)
                if mic_buffer else np.array([], dtype=np.int16)
            )

        save_audio(
            mic_data,
            MIC_DIR,
            "user",
        )

        # Save agent recording
        with agent_lock:
            agent_data = (
                np.concatenate(agent_buffer)
                if agent_buffer else np.array([], dtype=np.int16)
            )

        save_audio(
            agent_data,
            AGENT_DIR,
            "agent",
        )

        await room.disconnect()
        if hasattr(audio_source, "aclose"):
            await audio_source.aclose()
        elif hasattr(audio_source, "close"):
            audio_source.close()

        print("Recordings saved successfully!")


# ==========================================
# 13. RUN APPLICATION
# ==========================================

if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("Simulator stopped.")

    except Exception as error:
        print("Error:", error)
        raise
