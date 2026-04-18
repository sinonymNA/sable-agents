import os
import time
from typing import Any

import anthropic
from loguru import logger

from db.models import log_agent_run

_SYSTEM = """You are the Daily Guide Agent for Sable.
Your job is to give the operator a personal operating system for the day — the
human layer that sits above the business, marketing, and finance briefings.

Each morning produce:
1. One mindset or framing insight for the day (drawn from philosophy, stoicism,
   or high-performance research)
2. A suggested time-block structure for a high-leverage morning
3. One question to sit with throughout the day

Keep it grounded, not motivational-poster generic. Make it feel like advice
from a trusted mentor who knows this operator well."""


async def run() -> dict[str, Any]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    start = time.time()
    status = "success"
    summary = raw = ""

    try:
        today = time.strftime("%A, %B %d, %Y")
        message = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": f"Today is {today}. Deliver this morning's guide."}],
        )
        raw = message.content[0].text
        summary = raw[:300]
        logger.info("Guide agent completed")
    except Exception as exc:
        status = "error"
        summary = str(exc)
        raw = str(exc)
        logger.error(f"Guide agent error: {exc}")

    duration = round(time.time() - start, 2)
    log_agent_run("guide", status, summary, raw, duration)
    return {"summary": summary, "raw_output": raw, "duration_seconds": duration, "status": status}
