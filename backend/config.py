# ─────────────────────────────────────────────
# config.py  –  Central configuration
# Add / remove languages here only.
# ─────────────────────────────────────────────

SUPPORTED_LANGUAGES: dict[str, dict] = {
    "hi": {
        "name": "Hindi",
        "tts_voice": "hi-IN-SwaraNeural",
    },
    "en": {
        "name": "English",
        "tts_voice": "en-IN-NeerjaNeural",       # Indian-English voice
    },
    "ta": {
        "name": "Tamil",
        "tts_voice": "ta-IN-PallaviNeural",
    },
    # ── Easily add Bengali back by uncommenting: ──
    # "bn": {
    #     "name": "Bengali",
    #     "tts_voice": "bn-IN-TanishaaNeural",
    # },
}

# Whisper model: "tiny" / "base" / "small"
# base  → ~2 GB RAM, good accuracy, reasonable CPU speed
# tiny  → ~1 GB RAM, fastest,  lower accuracy
WHISPER_MODEL_SIZE = "base"
WHISPER_COMPUTE_TYPE = "int8"          # CPU-friendly

# How many 1-second audio chunks to buffer before running ASR
# 3  → ~3 s latency, better accuracy
# 2  → ~2 s latency, slightly worse accuracy
BUFFER_CHUNK_COUNT = 3

# Maximum listeners per room
MAX_LISTENERS_PER_ROOM = 50
