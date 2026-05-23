import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.websockets import WebSocketState

from room_manager import RoomManager
from asr.whisper_engine import WhisperEngine
from translation.translator import Translator
from tts.tts_engine import TTSEngine
from streaming.audio_processor import AudioProcessor
from config import SUPPORTED_LANGUAGES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── Global singletons ─────────────────────────────────────────────────────────

room_manager = RoomManager()
whisper_engine: WhisperEngine | None = None
translator: Translator | None = None
tts_engine: TTSEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global whisper_engine, translator, tts_engine
    logger.info("═══ Loading AI engines … ═══")
    # Run Whisper load in thread-pool (it's CPU-bound / blocking)
    loop = asyncio.get_event_loop()
    whisper_engine = await loop.run_in_executor(None, WhisperEngine)
    translator = Translator()
    tts_engine = TTSEngine()
    logger.info("═══ All engines ready. ═══")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Real-Time Multilingual Translation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
app.mount("/static", StaticFiles(directory="../frontend"), name="static")


# ── HTTP routes ───────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("../frontend/speaker.html")

@app.get("/listener")
async def listener_page():
    return FileResponse("../frontend/listener.html")

@app.post("/room/create")
async def create_room():
    room_id = room_manager.create_room()
    logger.info(f"Room created via HTTP: {room_id}")
    return {"room_id": room_id}

@app.get("/room/{room_id}/exists")
async def room_exists(room_id: str):
    if not room_manager.room_exists(room_id):
        raise HTTPException(status_code=404, detail="Room not found")
    return {
        "exists": True,
        "listener_count": room_manager.get_listener_count(room_id),
    }

@app.get("/languages")
async def list_languages():
    return {
        code: {"name": cfg["name"], "tts_voice": cfg["tts_voice"]}
        for code, cfg in SUPPORTED_LANGUAGES.items()
    }

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── WebSocket: Speaker ────────────────────────────────────────────────────────

@app.websocket("/ws/speaker/{room_id}")
async def speaker_websocket(websocket: WebSocket, room_id: str):
    await websocket.accept()

    if not room_manager.room_exists(room_id):
        await websocket.close(code=4004, reason="Room not found")
        return

    room_manager.set_speaker(room_id, websocket)
    processor = AudioProcessor(
        room_id=room_id,
        room_manager=room_manager,
        whisper_engine=whisper_engine,
        translator=translator,
        tts_engine=tts_engine,
    )

    logger.info(f"Speaker connected → room {room_id}")
    try:
        while True:
            # Receive binary audio chunk from browser MediaRecorder
            chunk = await websocket.receive_bytes()
            await processor.process_chunk(chunk)

    except WebSocketDisconnect:
        logger.info(f"Speaker disconnected from room {room_id}")
    except Exception as exc:
        logger.error(f"Speaker WS error in {room_id}: {exc}")
    finally:
        room_manager.remove_speaker(room_id)


# ── WebSocket: Listener ───────────────────────────────────────────────────────

@app.websocket("/ws/listener/{room_id}")
async def listener_websocket(
    websocket: WebSocket,
    room_id: str,
    lang: str = Query(default="en"),
):
    await websocket.accept()

    if not room_manager.room_exists(room_id):
        await websocket.close(code=4004, reason="Room not found")
        return

    import uuid
    listener_id = uuid.uuid4().hex[:8]
    success = room_manager.add_listener(room_id, listener_id, websocket, lang)
    if not success:
        await websocket.close(code=4003, reason="Room full")
        return

    # Confirm join to client
    await websocket.send_json({
        "type": "joined",
        "listener_id": listener_id,
        "language": lang,
        "language_name": SUPPORTED_LANGUAGES.get(lang, {}).get("name", lang),
    })

    logger.info(f"Listener {listener_id} connected → room {room_id} [{lang}]")

    try:
        # Keep connection alive; handle pings from client
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=25.0)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Server-initiated heartbeat
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        logger.info(f"Listener {listener_id} disconnected from room {room_id}")
    except Exception as exc:
        logger.error(f"Listener WS error [{listener_id}]: {exc}")
    finally:
        room_manager.remove_listener(room_id, listener_id)
