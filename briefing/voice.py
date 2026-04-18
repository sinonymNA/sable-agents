import os
import tempfile
from pathlib import Path

import httpx
from loguru import logger

_ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"


async def generate_audio(script: str, voice_id: str) -> str:
    """Convert script to MP3 using ElevenLabs. Returns local file path."""
    api_key = os.environ["ELEVENLABS_API_KEY"]
    url = f"{_ELEVENLABS_BASE}/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": script,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir="/tmp")
    tmp.write(response.content)
    tmp.close()

    logger.info(f"Audio generated: {tmp.name} ({len(response.content)} bytes)")
    return tmp.name
