# Real-Time Multilingual Translation System

Backend-focused MVP — one speaker, multiple listeners, live translated subtitles + audio.

---

## Supported Languages

| Code | Language | TTS Voice           |
|------|----------|---------------------|
| `hi` | Hindi    | hi-IN-SwaraNeural   |
| `en` | English  | en-IN-NeerjaNeural  |
| `ta` | Tamil    | ta-IN-PallaviNeural |

> To add Bengali (or any language), uncomment the `bn` block in `backend/config.py`.  
> No other code changes needed.

---

## Prerequisites

- Python 3.10+
- **ffmpeg** installed on the system (required by Whisper for audio decoding)

```bash
# Ubuntu / Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

---

## Setup & Run

```bash
# 1. Clone / extract project
cd multilang-translation

# 2. Create virtualenv (recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the server
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

On first start, Whisper will download the `base` model (~150 MB). This happens once.

---

## Usage

| Role     | URL                              |
|----------|----------------------------------|
| Speaker  | http://localhost:8000/           |
| Listener | http://localhost:8000/listener   |

1. **Speaker** opens the speaker page, clicks **Create Room**, shares the 8-character code.
2. **Listener** opens the listener page on any device (same network), enters the code, selects language, clicks **Join Room**.
3. Speaker clicks **Start Mic** — translations appear on listener screens within ~3 seconds.

---

## Architecture

```
Speaker Browser
      │
      │  binary webm/opus chunks (1 s each, via MediaRecorder)
      ▼
FastAPI WebSocket  /ws/speaker/{room_id}
      │
      │  Buffer 3 chunks (~3 s of audio)
      ▼
WhisperEngine  (faster-whisper, CPU int8)
      │  transcript + detected language
      ▼
Translator  (deep-translator, asyncio.gather)
      │  translations for all active listener languages
      ▼
  ┌───┴────────────────────────────┐
  │  Subtitle broadcast (instant)  │  ← subtitle-first architecture
  └────────────────────────────────┘
      │
      ▼
TTSEngine  (edge-tts, async, once per language)
      │  mp3 bytes per language
      ▼
  ┌───┴──────────────────────────────────────────┐
  │  Audio broadcast to all listeners by language │
  └──────────────────────────────────────────────┘
```

### Key design decisions

**Subtitle-first:** Translations are pushed to listeners *before* TTS generation starts.  
Listeners read the text immediately (~1–2 s) while audio arrives a second later.

**TTS de-duplication:** TTS is generated *once per language* per audio chunk, regardless  
of how many listeners share that language. 10 Tamil listeners → 1 Tamil TTS call.

**Translation de-duplication:** Same — one translation API call per target language.

**Non-blocking pipeline:** `asyncio.create_task()` fires the pipeline without blocking  
the WebSocket receive loop, so the speaker never stalls.

---

## Latency Breakdown

| Stage                | Typical time (CPU) |
|----------------------|--------------------|
| Audio buffering      | ~3 s (configurable)|
| Whisper `base` ASR   | 1–3 s              |
| Translation (3 langs)| 0.5–1.5 s          |
| Subtitle delivery    | ~0 ms after above  |
| Edge-TTS (3 langs)   | 1–3 s              |
| **Total (subtitle)** | **~5–7 s**         |
| **Total (audio)**    | **~7–10 s**        |

To reduce latency: use `tiny` model (`WHISPER_MODEL_SIZE = "tiny"`) or `BUFFER_CHUNK_COUNT = 2`.

---

## Scalability

**Current (single process):**
- All state is in-memory in `RoomManager`.
- Supports ~10–20 simultaneous listeners per CPU core comfortably.
- Each WebSocket is a lightweight asyncio coroutine — no threads per connection.

**Horizontal scaling path:**
1. Replace in-memory `RoomManager` with Redis (pub/sub for broadcast, hash for room state).
2. Run multiple Uvicorn workers behind an Nginx reverse proxy with sticky sessions.
3. Move Whisper inference to a dedicated worker queue (Celery + Redis) to isolate CPU load.
4. Use a CDN or WebRTC relay for audio delivery at scale.

---

## Project Structure

```
multilang-translation/
├── backend/
│   ├── main.py                  ← FastAPI app, WebSocket endpoints
│   ├── config.py                ← Languages, model sizes, tuning knobs
│   ├── room_manager.py          ← Room state, listener groups, broadcast
│   ├── asr/
│   │   └── whisper_engine.py    ← faster-whisper, CPU int8, thread-pool
│   ├── translation/
│   │   └── translator.py        ← deep-translator, concurrent gather
│   ├── tts/
│   │   └── tts_engine.py        ← edge-tts, once per language
│   └── streaming/
│       └── audio_processor.py   ← Pipeline orchestrator, buffering
├── frontend/
│   ├── speaker.html / speaker.js
│   ├── listener.html / listener.js
│   └── styles.css
├── requirements.txt
└── README.md
```

---

## Configuration (`backend/config.py`)

| Setting               | Default  | Effect                                 |
|-----------------------|----------|----------------------------------------|
| `WHISPER_MODEL_SIZE`  | `"base"` | `"tiny"` = faster, less accurate       |
| `BUFFER_CHUNK_COUNT`  | `3`      | Lower = less latency, lower accuracy   |
| `MAX_LISTENERS_PER_ROOM` | `50`  | Hard cap per room                      |
| `SUPPORTED_LANGUAGES` | 3 langs  | Add/remove language + voice entries    |
