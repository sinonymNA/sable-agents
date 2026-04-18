import os
import time
from typing import Any

import anthropic
from loguru import logger

from db.models import log_agent_run

_SYSTEM = """You are the Business Intelligence Agent for Sable.
Your job is to surface the most important business developments relevant to a
founder-operator running a small, high-growth company.

Each morning you will be given the current date. Produce a concise briefing
covering:
1. Macro business climate (2-3 sentences)
2. Key market moves or competitor signals worth watching
3. One operational focus recommendation for the day

Be direct, specific, and action-oriented. No filler."""


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
            messages=[{"role": "user", "content": f"Today is {today}. Deliver this morning's business briefing."}],
        )
        raw = message.content[0].text
        summary = raw[:300]
        logger.info("Business agent completed")
    except Exception as exc:
        status = "error"
        summary = str(exc)
        raw = str(exc)
        logger.error(f"Business agent error: {exc}")

    duration = round(time.time() - start, 2)
    log_agent_run("business", status, summary, raw, duration)
    return {"summary": summary, "raw_output": raw, "duration_seconds": duration, "status": status}
