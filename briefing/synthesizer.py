import os
from typing import Any

import anthropic
from loguru import logger

_SYSTEM = """You are the Sable Briefing Synthesizer.
You receive four agent reports — Business, Marketing, Finance, and Guide — and
weave them into a single, natural-sounding voice briefing script.

Rules:
- Write for the ear, not the eye. Short sentences. Active voice.
- Total length: 3–4 minutes when read aloud (~400-550 words).
- Open with a greeting and the date. Close with an energising send-off.
- Transition naturally between sections; no robotic headers.
- Preserve every actionable insight from the source reports.
- Do NOT add fabricated facts. If a section is thin, compress it gracefully."""


async def synthesize(
    business: dict[str, Any],
    marketing: dict[str, Any],
    finance: dict[str, Any],
    guide: dict[str, Any],
) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = f"""Here are today's four agent reports. Synthesize them into a single voice briefing script.

--- BUSINESS ---
{business.get('raw_output', business.get('summary', ''))}

--- MARKETING ---
{marketing.get('raw_output', marketing.get('summary', ''))}

--- FINANCE ---
{finance.get('raw_output', finance.get('summary', ''))}

--- GUIDE ---
{guide.get('raw_output', guide.get('summary', ''))}

Now write the voice briefing script."""

    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    script = message.content[0].text
    logger.info(f"Briefing synthesized ({len(script)} chars)")
    return script
