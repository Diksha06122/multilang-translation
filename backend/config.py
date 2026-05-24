SUPPORTED_LANGUAGES: dict[str, dict] = {
    "hi": {
        "name": "Hindi",
        "tts_voice": "hi-IN-SwaraNeural",
    },
    "en": {
        "name": "English",
        "tts_voice": "en-IN-NeerjaNeural",     
    },
    "ta": {
        "name": "Tamil",
        "tts_voice": "ta-IN-PallaviNeural",
    },

    "bn": {
        "name": "Bengali",
        "tts_voice": "bn-IN-TanishaaNeural",
    },
}

WHISPER_MODEL_SIZE = "base"
WHISPER_MODEL_PATH = None

WHISPER_COMPUTE_TYPE = "int8"          


BUFFER_CHUNK_COUNT = 3

# Maximum listeners per room
MAX_LISTENERS_PER_ROOM = 50
