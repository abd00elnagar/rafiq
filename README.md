# Voice Agent (ESP32 + PC)

## Getting Started

1. Create virtual environment and install dependencies:
```bash
python -m venv .venv
# Activate environment (Windows PowerShell):
.\.venv\Scripts\Activate.ps1
# Install dependencies:
pip install -r requirements.txt
```
*(Note: Make sure `ffmpeg` is installed and added to your system PATH for TTS).*

2. Configure OpenRouter API Key:
- Copy `.env.example` to `.env`
- Set your key: `OPENROUTER_API_KEY=your_key`

3. Run Server and Simulator Client:
```bash
python -m server.server              # Terminal 1 (Server)
python sim_client/sim_client.py      # Terminal 2 (PC Simulator Client)
```

To test the LLM standalone:
```bash
python -m server.llm
```

## Protocol (Contract between Client and Server)
**Audio:** PCM 16-bit, mono, 16000 Hz, little-endian, streamed over binary frames. (Packet size ≈ 40ms = 1280 bytes)

**Client -> Server (text/JSON):**
| Message | Meaning |
|---|---|
| `{"type":"start"}` | User started speaking (binary audio frames stream after) |
| `{"type":"end"}` | Finished speaking, begin processing pipeline |

**Server -> Client:**
| Message | Meaning |
|---|---|
| `{"type":"state","state":"listening/thinking/speaking/idle"}` | State notification (e.g. for ESP32 LED status) |
| `{"type":"transcript","role":"user/assistant","text":"..."}` | Transcript for debugging and display |
| binary frames | Synthesized audio response (same format) |
| `{"type":"tts_end"}` | Audio response playback finished |

## Request Pipeline
`mic -> [start] + chunks + [end] -> STT -> LLM -> TTS -> chunks -> speaker`

## Development Roadmap
1. Test each module independently (`python -m server.stt / llm / tts`)
2. Run full conversation loop via `sim_client`
3. Add VAD (Silero) to replace manual Enter key + support barge-in interruption
4. Add MCP tools inside `llm.py`
5. Implement ESP32 firmware adhering to this protocol

