import os
import tempfile

import httpx
from loguru import logger

_ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"


def convert_to_audio(script: str, date_str: str) -> str | None:
    """Convert script to MP3, save to /tmp/briefing_{date}.mp3, return public URL."""
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_BUSINESS", "")

    if not api_key or not voice_id:
        logger.warning("ElevenLabs credentials not configured — skipping audio generation")
        return None

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

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
    except Exception as exc:
        logger.error(f"ElevenLabs audio generation failed: {exc}")
        return None

    filename = f"briefing_{date_str}.mp3"
    filepath = f"/tmp/{filename}"
    with open(filepath, "wb") as f:
        f.write(response.content)

    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    if not domain:
        logger.warning("RAILWAY_PUBLIC_DOMAIN not set — audio saved locally but no public URL")
        return None

    audio_url = f"https://{domain}/audio/{filename}"
    logger.info(f"Audio generated: {filepath} → {audio_url} ({len(response.content)} bytes)")
    return audio_url


async def generate_audio(script: str, voice_id: str) -> str:
    """Convert script to MP3 using ElevenLabs. Returns local file path."""
    import httpx as _httpx

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

    async with _httpx.AsyncClient(timeout=120) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir="/tmp")
    tmp.write(response.content)
    tmp.close()

    logger.info(f"Audio generated: {tmp.name} ({len(response.content)} bytes)")
    return tmp.name
