import os
import time
from typing import Any

import anthropic
from loguru import logger

from db.models import log_agent_run

_SYSTEM = """You are the Marketing Intelligence Agent for Sable.
Your job is to identify the highest-leverage marketing opportunities and signals
for a founder growing an audience and customer base.

Each morning produce a concise briefing covering:
1. Trending topics or conversations relevant to the brand (2-3 items)
2. Content opportunity of the day — a specific angle worth publishing
3. One distribution or growth tactic to try this week

Be direct and specific. Give the operator something they can act on immediately."""


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
            messages=[{"role": "user", "content": f"Today is {today}. Deliver this morning's marketing briefing."}],
        )
        raw = message.content[0].text
        summary = raw[:300]
        logger.info("Marketing agent completed")
    except Exception as exc:
        status = "error"
        summary = str(exc)
        raw = str(exc)
        logger.error(f"Marketing agent error: {exc}")

    duration = round(time.time() - start, 2)
    log_agent_run("marketing", status, summary, raw, duration)
    return {"summary": summary, "raw_output": raw, "duration_seconds": duration, "status": status}
