"""
tts/tts_engine.py
Wraps edge-tts for multilingual TTS.

Key design decisions:
  • edge-tts is natively async — no thread-pool needed.
  • TTS is generated ONCE per language per audio chunk, then
    broadcast to ALL listeners of that language (no duplication).
  • Audio is returned as mp3 bytes.
"""

import asyncio
import io
import logging
import edge_tts
from config import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

# Build voice map from config
VOICE_MAP: dict[str, str] = {
    lang: cfg["tts_voice"]
    for lang, cfg in SUPPORTED_LANGUAGES.items()
}


class TTSEngine:
    def __init__(self):
        logger.info(f"TTS engine ready. Voices: {VOICE_MAP}")

    async def synthesize(self, text: str, language: str) -> bytes:
        """
        Convert *text* to mp3 bytes using the Edge-TTS voice for *language*.
        Returns empty bytes on failure (callers should handle gracefully).
        """
        if not text.strip():
            return b""

        voice = VOICE_MAP.get(language)
        if not voice:
            logger.warning(f"No TTS voice configured for language '{language}'")
            return b""

        try:
            communicate = edge_tts.Communicate(text=text, voice=voice)
            mp3_buffer = io.BytesIO()

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_buffer.write(chunk["data"])

            audio_bytes = mp3_buffer.getvalue()
            logger.debug(f"TTS [{language}]: {len(audio_bytes)} bytes generated.")
            return audio_bytes

        except Exception as exc:
            logger.error(f"TTS synthesis error for '{language}': {exc}")
            return b""

    async def synthesize_all(
        self,
        translations: dict[str, str],   # {"hi": "...", "ta": "..."}
        target_languages: set[str],
    ) -> dict[str, bytes]:
        """
        Generate TTS for all required languages concurrently.
        Returns {"hi": mp3_bytes, "ta": mp3_bytes}
        """
        tasks = {
            lang: self.synthesize(translations.get(lang, ""), lang)
            for lang in target_languages
            if lang in translations
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        lang_audio: dict[str, bytes] = {}
        for lang, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning(f"TTS gather error for '{lang}': {result}")
            elif result:
                lang_audio[lang] = result

        return lang_audio
