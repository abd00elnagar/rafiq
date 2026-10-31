
import logging
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    AgentServer,
)

# Load .env from the same directory as agent.py
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

logging.basicConfig(level=logging.INFO)

server = AgentServer()


@server.rtc_session()
async def voice_agent(ctx: agents.JobContext):

    logging.info("Agent job received")

    # AgentSession handles the room connection.
    # Do not call ctx.connect() separately here.

    session = AgentSession(
        stt="deepgram/nova-3",
        llm="openai/gpt-4.1-mini",
        tts="cartesia/sonic-3",
    )

    await session.start(
        room=ctx.room,
        agent=Agent(
            instructions="""
            You are Rafiq, a friendly voice assistant.

            Listen carefully to the user.
            Answer naturally.
            Keep your answers concise.
            """
        ),
    )

    logging.info("Voice agent session started")


if __name__ == "__main__":
    agents.cli.run_app(server)
