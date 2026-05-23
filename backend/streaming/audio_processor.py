"""
streaming/audio_processor.py

Orchestrates the full pipeline per room:
    audio chunks → buffer → ASR → translate → [subtitle broadcast] → TTS → [audio broadcast]

Design:
  • Buffers N chunks (default 3 × ~1 s) before running ASR.
  • Subtitles are sent BEFORE TTS starts (subtitle-first architecture).
  • TTS is generated once per language per pipeline run.
  • Uses asyncio.create_task() so buffering never blocks WebSocket receive.
"""

import asyncio
import logging
from asr.whisper_engine import WhisperEngine
from translation.translator import Translator
from tts.tts_engine import TTSEngine
from room_manager import RoomManager
from config import BUFFER_CHUNK_COUNT

logger = logging.getLogger(__name__)


class AudioProcessor:
    def __init__(
        self,
        room_id: str,
        room_manager: RoomManager,
        whisper_engine: WhisperEngine,
        translator: Translator,
        tts_engine: TTSEngine,
    ):
        self.room_id = room_id
        self.room_manager = room_manager
        self.whisper_engine = whisper_engine
        self.translator = translator
        self.tts_engine = tts_engine

        self._audio_buffer = bytearray()
        self._chunk_count = 0
        self._pipeline_running = False   # Prevent overlapping pipeline calls
        self._header = None              # Store the first chunk (WebM header)

    # ── Public API ────────────────────────────────────────────────

    async def process_chunk(self, chunk: bytes):
        """
        Called for every audio chunk received from the speaker WebSocket.
        Appends chunk to buffer; fires pipeline when buffer is full.
        """
        # Capture the first chunk as the header (contains WebM metadata)
        if self._header is None:
            self._header = chunk

        self._audio_buffer.extend(chunk)
        self._chunk_count += 1

        if self._chunk_count >= BUFFER_CHUNK_COUNT:
            # Prepend header if it's not already at the start of this segment
            # (The very first batch already has the header naturally)
            payload = bytes(self._audio_buffer)
            if self._header and not payload.startswith(self._header):
                payload = self._header + payload

            self._audio_buffer = bytearray()
            self._chunk_count = 0
            
            # Fire-and-forget; does NOT await so WebSocket stays unblocked
            asyncio.create_task(self._run_pipeline(payload))

    # ── Pipeline ──────────────────────────────────────────────────

    async def _run_pipeline(self, audio_data: bytes):
        """Full ASR → translate → subtitle → TTS → audio pipeline."""
        if self._pipeline_running:
            logger.debug(f"[{self.room_id}] Pipeline busy, dropping chunk.")
            return

        self._pipeline_running = True
        try:
            await self._pipeline(audio_data)
        except Exception as exc:
            logger.error(f"[{self.room_id}] Pipeline error: {exc}", exc_info=True)
        finally:
            self._pipeline_running = False

    async def _pipeline(self, audio_data: bytes):
        # ── 1. ASR ────────────────────────────────────────────────
        asr_result = await self.whisper_engine.transcribe(audio_data)
        text = asr_result.get("text", "").strip()
        detected_lang = asr_result.get("language", "unknown")

        if not text:
            logger.debug(f"[{self.room_id}] Empty transcript — skipping.")
            return

        logger.info(f"[{self.room_id}] ASR [{detected_lang}]: {text!r}")

        # ── 2. Determine active listener languages ─────────────────
        active_langs = self.room_manager.get_active_languages(self.room_id)
        if not active_langs:
            logger.debug(f"[{self.room_id}] No active listeners.")
            return

        # ── 3. Translate to all active languages concurrently ──────
        translations = await self.translator.translate_all(text, active_langs)
        logger.debug(f"[{self.room_id}] Translations: {translations}")

        # ── 4. Subtitle-first broadcast ────────────────────────────
        await self.room_manager.broadcast_subtitles(self.room_id, translations)

        # ── 5. TTS — once per language, then broadcast ─────────────
        lang_audio = await self.tts_engine.synthesize_all(translations, active_langs)
        await self.room_manager.broadcast_audio(self.room_id, lang_audio)

        logger.info(
            f"[{self.room_id}] Pipeline complete — "
            f"langs={list(active_langs)}, "
            f"tts_generated={list(lang_audio.keys())}"
        )
