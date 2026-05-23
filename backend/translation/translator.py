"""
translation/translator.py
Uses deep-translator (GoogleTranslator backend) — a stable, maintained
replacement for the broken googletrans library.

Translation is done concurrently across all target languages using
asyncio.gather() to minimise latency.
"""

import asyncio
import logging
from deep_translator import GoogleTranslator
from config import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

# Language codes supported by deep-translator / Google Translate
# These match the keys in config.SUPPORTED_LANGUAGES
_LANG_MAP: dict[str, str] = {
    "hi": "hi",
    "en": "en",
    "ta": "ta",
    "bn": "bn",
}


class Translator:
    def __init__(self):
        self._loop = asyncio.get_event_loop()
        logger.info("Translator ready (deep-translator / Google backend).")

    # ── Public API ────────────────────────────────────────────────

    async def translate_all(
        self,
        text: str,
        target_languages: set[str],
    ) -> dict[str, str]:
        """
        Translate *text* into every language in *target_languages* concurrently.
        Returns {"hi": "...", "ta": "...", "en": "..."}
        """
        if not text.strip():
            return {}

        tasks = {
            lang: self._translate_async(text, lang)
            for lang in target_languages
            if lang in _LANG_MAP
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        translations: dict[str, str] = {}
        for lang, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning(f"Translation to '{lang}' failed: {result}")
                translations[lang] = text          # Fallback: original text
            else:
                translations[lang] = result

        return translations

    # ── Internal ──────────────────────────────────────────────────

    async def _translate_async(self, text: str, target_lang: str) -> str:
        """Run synchronous deep-translator in a thread-pool."""
        return await self._loop.run_in_executor(
            None,
            self._sync_translate,
            text,
            target_lang,
        )

    @staticmethod
    def _sync_translate(text: str, target_lang: str) -> str:
        translated = GoogleTranslator(
            source="auto",
            target=_LANG_MAP[target_lang],
        ).translate(text)
        return translated or text
