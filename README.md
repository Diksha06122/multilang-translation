# Real-Time Multilingual Translation System


---

## Supported Languages

| Code | Language | TTS Voice           |
|------|----------|---------------------|
| `hi` | Hindi    | hi-IN-SwaraNeural   |
| `en` | English  | en-IN-NeerjaNeural  |
| `ta` | Tamil    | ta-IN-PallaviNeural |


---

## Prerequisites

- Python 3.10+
- **ffmpeg** installed on the system (required by Whisper for audio decoding)

```bash
# Ubuntu / Debian
sudo apt install ffmpeg

---

## Setup & Run

```bash
cd multilang-translation

# 2. Create virtualenv (recommended)
python -m venv venv
source venv/bin/activate     

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

## Configuration (`backend/config.py`)

| Setting               | Default  | Effect                                 |
|-----------------------|----------|----------------------------------------|
| `WHISPER_MODEL_SIZE`  | `"base"` | `"tiny"` = faster, less accurate       |
| `BUFFER_CHUNK_COUNT`  | `3`      | Lower = less latency, lower accuracy   |
| `MAX_LISTENERS_PER_ROOM` | `50`  | Hard cap per room                      |
| `SUPPORTED_LANGUAGES` | 3 langs  | Add/remove language + voice entries    |
