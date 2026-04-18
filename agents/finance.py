import os
import time
from typing import Any

import anthropic
from loguru import logger

from db.models import log_agent_run

_SYSTEM = """You are the Finance Intelligence Agent for Sable.
Your job is to give a founder-operator a crisp financial situational awareness
briefing each morning.

Cover:
1. Relevant macro / market conditions (interest rates, indices, sector moves)
2. Any cash-flow or runway considerations worth flagging (generic guidance)
3. One financial decision or review item for the day

Speak plainly. No jargon unless necessary. Be brief and actionable."""


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
            messages=[{"role": "user", "content": f"Today is {today}. Deliver this morning's finance briefing."}],
        )
        raw = message.content[0].text
        summary = raw[:300]
        logger.info("Finance agent completed")
    except Exception as exc:
        status = "error"
        summary = str(exc)
        raw = str(exc)
        logger.error(f"Finance agent error: {exc}")

    duration = round(time.time() - start, 2)
    log_agent_run("finance", status, summary, raw, duration)
    return {"summary": summary, "raw_output": raw, "duration_seconds": duration, "status": status}
