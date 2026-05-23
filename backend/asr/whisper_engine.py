"""
asr/whisper_engine.py
Wraps faster-whisper for CPU-friendly transcription.
Runs inference in a thread-pool to avoid blocking the event loop.
"""

import asyncio
import os
import tempfile
import logging
from faster_whisper import WhisperModel
from config import WHISPER_MODEL_SIZE, WHISPER_COMPUTE_TYPE

logger = logging.getLogger(__name__)


class WhisperEngine:
    def __init__(self, model_size: str = WHISPER_MODEL_SIZE):
        logger.info(f"Loading Whisper model '{model_size}' (CPU / {WHISPER_COMPUTE_TYPE})…")
        self.model = WhisperModel(
            model_size,
            device="cpu",
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        self._loop = asyncio.get_event_loop()
        logger.info("Whisper model ready.")

    # ── Public API ────────────────────────────────────────────────

    async def transcribe(self, audio_bytes: bytes) -> dict:
        """
        Accepts raw audio bytes (webm / opus / wav).
        Returns {"text": "...", "language": "hi", "confidence": 0.95}
        Runs synchronous Whisper in a thread-pool so it never blocks the loop.
        """
        return await self._loop.run_in_executor(None, self._sync_transcribe, audio_bytes)

    # ── Internal ──────────────────────────────────────────────────

    def _sync_transcribe(self, audio_bytes: bytes) -> dict:
        tmp_path = None
        try:
            # Write to temp file; faster-whisper uses ffmpeg to decode any format.
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name

            segments, info = self.model.transcribe(
                tmp_path,
                beam_size=5,
                vad_filter=True,                  # Skip silent segments
                vad_parameters={"min_silence_duration_ms": 500},
            )

            # Materialise the lazy generator before the file is deleted
            text = " ".join(seg.text.strip() for seg in segments).strip()

            return {
                "text": text,
                "language": info.language,
                "confidence": round(info.language_probability, 3),
            }

        except Exception as exc:
            logger.error(f"Whisper transcription error: {exc}")
            return {"text": "", "language": "unknown", "confidence": 0.0}

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
