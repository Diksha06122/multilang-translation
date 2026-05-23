"""
room_manager.py
Manages rooms, speakers, listeners, and broadcast logic.
All state is in-memory (single-process MVP).
"""

import uuid
import asyncio
import base64
import logging
from dataclasses import dataclass, field
from starlette.websockets import WebSocket, WebSocketState
from config import SUPPORTED_LANGUAGES, MAX_LISTENERS_PER_ROOM

logger = logging.getLogger(__name__)


@dataclass
class ListenerInfo:
    websocket: WebSocket
    language: str          # e.g. "hi", "ta", "en"
    listener_id: str


@dataclass
class Room:
    room_id: str
    speaker: WebSocket | None = None
    listeners: dict[str, ListenerInfo] = field(default_factory=dict)


class RoomManager:
    def __init__(self):
        self._rooms: dict[str, Room] = {}
        self._lock = asyncio.Lock()

    # ── Room lifecycle ────────────────────────────────────────────

    def create_room(self) -> str:
        room_id = uuid.uuid4().hex[:8].upper()
        self._rooms[room_id] = Room(room_id=room_id)
        logger.info(f"Room created: {room_id}")
        return room_id

    def room_exists(self, room_id: str) -> bool:
        return room_id in self._rooms

    def set_speaker(self, room_id: str, ws: WebSocket):
        if room_id in self._rooms:
            self._rooms[room_id].speaker = ws

    def remove_speaker(self, room_id: str):
        if room_id in self._rooms:
            self._rooms[room_id].speaker = None
            logger.info(f"Speaker left room {room_id}")

    # ── Listener management ───────────────────────────────────────

    def add_listener(self, room_id: str, listener_id: str, ws: WebSocket, language: str) -> bool:
        room = self._rooms.get(room_id)
        if not room:
            return False
        if len(room.listeners) >= MAX_LISTENERS_PER_ROOM:
            return False
        if language not in SUPPORTED_LANGUAGES:
            language = "en"                       # fallback
        room.listeners[listener_id] = ListenerInfo(
            websocket=ws,
            language=language,
            listener_id=listener_id,
        )
        logger.info(f"Listener {listener_id} joined room {room_id} ({language})")
        return True

    def remove_listener(self, room_id: str, listener_id: str):
        room = self._rooms.get(room_id)
        if room and listener_id in room.listeners:
            del room.listeners[listener_id]
            logger.info(f"Listener {listener_id} left room {room_id}")

    def get_active_languages(self, room_id: str) -> set[str]:
        """Return only the languages that have at least one active listener."""
        room = self._rooms.get(room_id)
        if not room:
            return set()
        return {info.language for info in room.listeners.values()}

    def get_listener_count(self, room_id: str) -> int:
        room = self._rooms.get(room_id)
        return len(room.listeners) if room else 0

    # ── Broadcast helpers ─────────────────────────────────────────

    async def broadcast_subtitles(
        self,
        room_id: str,
        translations: dict[str, str],   # {"hi": "...", "en": "...", "ta": "..."}
    ):
        """Send subtitle text to each listener in their language."""
        room = self._rooms.get(room_id)
        if not room:
            return

        tasks = []
        for info in list(room.listeners.values()):
            text = translations.get(info.language)
            if text:
                tasks.append(
                    self._safe_send_json(
                        info.websocket,
                        {"type": "subtitle", "text": text, "language": info.language},
                    )
                )
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_audio(
        self,
        room_id: str,
        lang_audio: dict[str, bytes],   # {"hi": mp3_bytes, "ta": mp3_bytes}
    ):
        """Send TTS audio (base64-encoded mp3) to each listener in their language."""
        room = self._rooms.get(room_id)
        if not room:
            return

        tasks = []
        for info in list(room.listeners.values()):
            audio_bytes = lang_audio.get(info.language)
            if audio_bytes:
                tasks.append(
                    self._safe_send_json(
                        info.websocket,
                        {
                            "type": "audio",
                            "language": info.language,
                            "data": base64.b64encode(audio_bytes).decode("utf-8"),
                            "mime": "audio/mpeg",
                        },
                    )
                )
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── Internal ──────────────────────────────────────────────────

    @staticmethod
    async def _safe_send_json(ws: WebSocket, payload: dict):
        try:
            if ws.client_state == WebSocketState.CONNECTED:
                await ws.send_json(payload)
        except Exception as exc:
            logger.warning(f"WebSocket send failed: {exc}")
