ESP32 Voice Agent – Python Simulation and Real Hardware Implementation
1. Project Overview

Our project is a voice assistant based on an ESP32 microcontroller connected to a Python backend using LiveKit.

The ESP32 captures the user's voice through a microphone and sends the audio to the backend. The backend processes the audio using a Voice AI pipeline and sends the generated voice response back to the ESP32.

Before implementing the physical ESP32, we will build a Python simulator that behaves like the ESP32.

The purpose of this simulation is to:

Test communication with LiveKit.
Test microphone audio streaming.
Test the voice-agent backend.
Test receiving and playing generated audio.
Debug the voice interaction without requiring physical hardware.
1.1 System Architecture
text
             DEVELOPMENT STAGE

       PC (ESP32 SIMULATOR)
       --------------------
       Python Program
       PC Microphone
       PC Speaker
              |
              |
          WebRTC
              |
              v
       LIVEKIT SERVER
              |
              |
              v
       PYTHON BACKEND
       --------------------
       LiveKit Agent
       Speech-to-Text
       LLM
       Text-to-Speech


The PC acts as the ESP32 during development.

When the real ESP32 is ready, we replace the Python simulator with the actual ESP32 firmware.

2. Technologies Used
Technology	Purpose
Python	Simulator and backend
LiveKit	Real-time audio communication
WebRTC	Audio transport
LiveKit Agents	Voice-agent framework
SoundDevice	PC microphone and speaker
NumPy	Audio data processing
STT	Speech recognition
LLM	Understanding and generating responses
TTS	Generating voice responses
ESP-IDF	Real ESP32 firmware development
I2S	Microphone and speaker communication
3. Project Folder Structure

We will organize the project as follows:

text
voice-agent-project/
│
├── backend/
│   │
│   ├── agent.py
│   ├── .env
│   └── requirements.txt
│
├── simulator/
│   │
│   ├── esp32_simulator.py
│   └── requirements.txt
│
└── README.md

Explanation of the files

backend/agent.py

The main Python voice-agent application.

Responsibilities:

Connect to the LiveKit room.
Receive microphone audio.
Process the user's speech.
Generate an AI response.
Send generated audio back to the room.

backend/.env

Stores API credentials and configuration.

simulator/esp32_simulator.py

Simulates the ESP32.

Responsibilities:

Connect to LiveKit.
Capture audio using the PC microphone.
Publish microphone audio.
Receive the agent's audio.
Play the response through the PC speaker.

README.md

Contains the project documentation and implementation instructions.

PART A: PYTHON SIMULATION
4. Preparing the Environment

Install Python 3.10 or newer.

Create and activate a virtual environment:

bash
python -m venv venv


Windows:

bash
venv\Scripts\activate


Linux/macOS:

bash
source venv/bin/activate


Install the required packages:

bash
pip install livekit livekit-agents python-dotenv
pip install livekit-plugins-deepgram
pip install livekit-plugins-openai
pip install livekit-plugins-cartesia
pip install sounddevice numpy


The STT, LLM and TTS providers above are examples. We can replace them with the providers already used by our existing voice agent.

5. LiveKit Configuration

We need a LiveKit server.

We can use LiveKit Cloud or a self-hosted LiveKit server.

Create a project and obtain:

LiveKit URL
API Key
API Secret

Create backend/.env:

env
LIVEKIT_URL=wss://your-project.livekit.cloud

LIVEKIT_API_KEY=your_api_key

LIVEKIT_API_SECRET=your_api_secret

DEEPGRAM_API_KEY=your_deepgram_key

OPENAI_API_KEY=your_openai_key

CARTESIA_API_KEY=your_cartesia_key


Never publish this file or upload it to GitHub.

The credentials shown here are development configuration. The simulator will use the LiveKit API credentials locally to create a temporary development token.

In production, the ESP32 must receive a short-lived token from a secure backend endpoint.

6. Backend Implementation

File: backend/agent.py

This file contains the LiveKit voice agent.

python
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, AgentServer

load_dotenv()

server = AgentServer()


@server.rtc_session()
async def voice_agent(ctx: agents.JobContext):

    print("Connecting to LiveKit...")

    # Connect the agent to the LiveKit room
    await ctx.connect()

    # Initialize the voice-agent pipeline
    session = AgentSession(
        stt="deepgram/nova-3",
        llm="openai/gpt-4.1-mini",
        tts="cartesia/sonic-3",
    )

    # Start the voice agent
    await session.start(
        room=ctx.room,
        agent=Agent(
            instructions="""
            You are a helpful voice assistant.

            Listen carefully to the user.
            Answer naturally.
            Keep your responses concise.
            """
        ),
    )

    print("Voice agent is ready!")


if __name__ == "__main__":
    agents.cli.run_app(server)

How does this backend work?

Step 1: Connect to LiveKit

The backend connects to the LiveKit room.

Step 2: Initialize the voice pipeline

The agent initializes three components:

STT: Converts speech into text.
LLM: Understands the request and generates an answer.
TTS: Converts the answer into speech.

Step 3: Start the agent

The agent listens for audio published by the simulator.

Step 4: Generate a response

After receiving the user's voice, the agent processes it and publishes the generated audio response.

LiveKit handles the audio communication between the participants.

7. ESP32 Simulator Implementation

File: simulator/esp32_simulator.py

This is the most important file for our simulation.

It acts as the ESP32 using the PC's microphone and speaker.

python
import asyncio
import os
from pathlib import Path

import numpy as np
import sounddevice as sd

from dotenv import load_dotenv
from livekit import rtc, api


# Load backend environment variables
ENV_PATH = (
    Path(__file__).resolve().parents[1]
    / "backend"
    / ".env"
)

load_dotenv(ENV_PATH)


LIVEKIT_URL = os.getenv("LIVEKIT_URL")
API_KEY = os.getenv("LIVEKIT_API_KEY")
API_SECRET = os.getenv("LIVEKIT_API_SECRET")

ROOM_NAME = "esp32-test-room"
IDENTITY = "python-esp32-simulator"

SAMPLE_RATE = 48000
CHANNELS = 1
FRAME_MS = 20

SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000


# Generate a temporary LiveKit access token
def create_token():

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


async def main():

    loop = asyncio.get_running_loop()

    # Create LiveKit room
    room = rtc.Room()

    # Create microphone audio source
    audio_source = rtc.AudioSource(
        sample_rate=SAMPLE_RATE,
        num_channels=CHANNELS,
    )

    # Create microphone track
    audio_track = rtc.LocalAudioTrack.create_audio_track(
        "esp32-microphone",
        audio_source,
    )

    # Receive and play agent audio
    async def play_audio(track):

        print("Agent audio received!")

        audio_stream = rtc.AudioStream(
            track,
            sample_rate=SAMPLE_RATE,
            num_channels=CHANNELS,
        )

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
                )

                speaker.write(audio_data)

    # Listen for audio tracks from the agent
    @room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant):

        if track.kind == rtc.TrackKind.KIND_AUDIO:

            asyncio.create_task(
                play_audio(track)
            )

    # Connect to LiveKit
    print("Connecting to LiveKit...")

    await room.connect(
        LIVEKIT_URL,
        create_token(),
    )

    print("Connected to room:", ROOM_NAME)

    # Publish microphone audio
    await room.local_participant.publish_track(
        audio_track
    )

    print("Microphone published!")

    # Capture PC microphone audio
    def microphone_callback(
        indata,
        frames,
        time,
        status,
    ):

        if status:
            print("Microphone status:", status)

        pcm = np.asarray(
            indata[:, 0],
            dtype=np.int16,
        )

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

    # Start microphone stream
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=SAMPLES_PER_FRAME,
        callback=microphone_callback,
    ):

        print("ESP32 Simulator is running!")
        print("Speak into your PC microphone.")

        try:
            await asyncio.Future()

        finally:
            await room.disconnect()
            audio_source.close()


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("Simulator stopped.")

Understanding the simulator

The simulator performs four main operations.

1. Connect to LiveKit

It joins the room using an access token.

2. Capture microphone audio

The PC microphone captures the user's voice.

SoundDevice reads the audio and NumPy prepares the audio samples.

3. Publish audio

The simulator publishes the microphone audio as a LiveKit audio track.

4. Receive the response

The simulator subscribes to the agent's audio track and plays the received audio through the PC speaker.

The PC therefore replaces the ESP32 microphone and speaker during development.

Note: This is a starting implementation. Audio device compatibility, microphone sample rate, callback buffering, playback synchronization and echo cancellation should be tested and improved before treating it as a stable real-time simulator.

8. Running the Simulation

Open two terminals.

Terminal 1: Start the backend
bash
cd backend

python agent.py dev

Terminal 2: Start the simulator
bash
cd simulator

python esp32_simulator.py


Expected output:

text
Connecting to LiveKit...
Connected to room: esp32-test-room

Microphone published!

ESP32 Simulator is running!
Speak into your PC microphone.


When the agent joins:

text
Voice agent is ready!


When the agent sends a response:

text
Agent audio received!

Testing procedure
Make sure your PC microphone is connected.
Make sure your speakers or headphones are working.
Start the backend.
Start the simulator.
Speak into the microphone.
Wait for the AI response.
Listen to the generated response.

Important: Use headphones during initial tests to prevent the speaker output from being captured again by the microphone.

PART B: HOW THE REAL ESP32 WILL WORK
9. Transition from Simulation to Hardware

Once the simulation works correctly, we can move to the physical ESP32.

The main difference is that we replace the PC microphone and speaker with actual hardware.

Simulation	Real implementation
PC microphone	ESP32 microphone
PC speaker	ESP32 speaker
Python program	ESP32 firmware
SoundDevice	I2S audio interface
PC Wi-Fi	ESP32 Wi-Fi
Python LiveKit SDK	LiveKit ESP32 SDK
Same LiveKit room	Same LiveKit room
Same Python agent	Same Python agent

The voice-agent backend does not need to be rewritten simply because we changed the client hardware.

10. Recommended Hardware

For the actual implementation, we should consider:

ESP32-S3 development board.
I2S microphone.
I2S audio amplifier or audio codec.
Speaker.
USB cable and power supply.
Wi-Fi connection.

An ESP32-S3 board with integrated audio hardware is preferable for development.

The exact microphone and speaker connections depend on the selected board.

11. Real ESP32 Architecture
text
              USER
               |
               v
        I2S MICROPHONE
               |
               v
          ESP32-S3
               |
        LiveKit ESP32 SDK
               |
         Wi-Fi / WebRTC
               |
               v
         LIVEKIT SERVER
               |
               v
        PYTHON BACKEND
               |
       +-------+-------+
       |       |       |
      STT     LLM     TTS
       |       |       |
       +-------+-------+
               |
               v
        LIVEKIT SERVER
               |
               v
          ESP32-S3
               |
        I2S AUDIO OUTPUT
               |
               v
            SPEAKER

12. Implementing LiveKit on ESP32

LiveKit provides an official ESP32 client SDK.

Repository:

https://github.com/livekit/client-sdk-esp32

Documentation:

https://docs.livekit.io/frontends/build/hardware/esp32/

Hardware requirements

The official SDK currently supports:

ESP32-S3
ESP32-P4

It requires ESP-IDF 5.4 or newer.

The SDK is currently in Developer Preview, so its APIs and limitations should be checked against the version we use.

Step 1: Install ESP-IDF

Install ESP-IDF using Espressif's official installation process.

https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/

Step 2: Create an ESP32 project

Use the official LiveKit example as the starting point.

For example:

bash
idf.py create-project-from-example \
"livekit/livekit=0.3.11:voice-ai"


Check the repository for the current SDK version and exact example name before running the command.

Step 3: Configure audio hardware

The ESP32 needs to initialize:

I2S microphone input.
I2S speaker output.
Audio capture.
Audio playback.

The LiveKit ESP32 SDK uses Espressif's audio capture and rendering components.

Step 4: Connect to Wi-Fi

The ESP32 connects to the internet using its Wi-Fi interface.

Step 5: Connect to LiveKit

The ESP32 receives a temporary access token from our backend and joins the configured LiveKit room.

Step 6: Publish microphone audio

The ESP32 captures audio and publishes it to LiveKit.

Step 7: Receive agent audio

The ESP32 subscribes to the agent's audio and plays it through the speaker.

Step 8: Test the complete system

The same Python voice-agent backend used during simulation should now communicate with the physical device.

PART C: DEVELOPMENT PLAN
13. Implementation Roadmap

We should divide the project into five stages.

Stage 1: Basic LiveKit connection

Goal: Make the Python simulator join a LiveKit room.

Tasks:

Configure LiveKit credentials.
Generate an access token.
Connect the simulator.
Confirm the participant appears in the room.

Expected result: The simulator successfully joins LiveKit.

Stage 2: Microphone streaming

Goal: Send PC microphone audio to LiveKit.

Tasks:

Capture microphone audio.
Convert audio into PCM frames.
Create a LiveKit audio track.
Publish the track.
Verify that the agent receives audio.

Expected result: The backend receives the user's voice.

Stage 3: Voice-agent integration

Goal: Connect the simulator to the existing voice agent.

Tasks:

Configure STT.
Configure LLM.
Configure TTS.
Process user speech.
Generate an audio response.

Expected result: The user can speak and receive an AI response.

Stage 4: Audio playback

Goal: Receive the generated voice from LiveKit.

Tasks:

Subscribe to the agent's audio track.
Receive audio frames.
Play the frames through the PC speaker.
Test latency and audio quality.

Expected result: The complete voice conversation works.

Stage 5: Real ESP32 implementation

Goal: Replace the PC simulator with the physical ESP32.

Tasks:

Prepare ESP32-S3.
Install ESP-IDF.
Add the official LiveKit ESP32 SDK.
Configure the microphone and speaker.
Configure Wi-Fi.
Implement secure token retrieval.
Join the LiveKit room.
Test bidirectional audio.

Expected result: The physical ESP32 communicates with the same Python voice-agent backend.

14. Final Expected Result

At the end of development, our project will have two implementations.

Development implementation:

text
PC Microphone
      |
      v
Python ESP32 Simulator
      |
      v
LiveKit
      |
      v
Python Voice Agent
      |
      v
LiveKit
      |
      v
PC Speaker


Final hardware implementation:

text
ESP32 Microphone
      |
      v
ESP32-S3 Firmware
      |
      v
LiveKit
      |
      v
Python Voice Agent
      |
      v
LiveKit
      |
      v
ESP32 Speaker


The same voice-agent backend can serve both implementations.

The simulator allows us to develop, test and debug most of the voice interaction before purchasing or integrating the physical hardware.

15. Important References
LiveKit Agents: https://docs.livekit.io/agents/
LiveKit AgentSession: https://docs.livekit.io/agents/logic/sessions/
LiveKit ESP32 documentation: https://docs.livekit.io/frontends/build/hardware/esp32/
Official ESP32 SDK: https://github.com/livekit/client-sdk-esp32
ESP-IDF documentation: https://docs.espressif.com/projects/esp-idf/

Project conclusion: We will first complete and test the Python ESP32 simulation. After confirming microphone streaming, AI processing and speaker playback, we will migrate the client side to ESP32-S3 hardware while keeping the LiveKit voice-agent backend.