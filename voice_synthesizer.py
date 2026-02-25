import os
import uuid
import logging

import httpx

logger = logging.getLogger(__name__)

AUDIO_DIR = "audio_cache"
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech"


async def synthesize_speech(text: str) -> str:
    """Convert text to speech via ElevenLabs. Returns the audio filename."""
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    api_key = os.getenv("ELEVENLABS_API_KEY", "")

    url = f"{ELEVENLABS_URL}/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()

    filename = f"{uuid.uuid4()}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)
    os.makedirs(AUDIO_DIR, exist_ok=True)

    with open(filepath, "wb") as f:
        f.write(resp.content)

    logger.info("Synthesized %d bytes of audio -> %s", len(resp.content), filename)
    return filename
