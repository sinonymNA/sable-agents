import os
from typing import Any

import anthropic
from loguru import logger

_SYSTEM = """You are the Sable Briefing Synthesizer.
You receive four agent reports — Finance, Business, Marketing, and Guide — and
weave them into a single, natural-sounding voice briefing script.

Rules:
- Write for the ear, not the eye. Short sentences. Active voice.
- Total length: 3–4 minutes when read aloud (~400-550 words).
- Open with a greeting and the date. Close with an energising send-off.
- Transition naturally between sections; no robotic headers.
- Preserve every actionable insight from the source reports.
- Do NOT add fabricated facts. If a section is thin, compress it gracefully."""


def synthesize(
    finance: dict[str, Any],
    business: dict[str, Any],
    marketing: dict[str, Any],
    guide: dict[str, Any],
) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — returning fallback briefing script")
        return (
            "Good morning. The Sable briefing pipeline completed agent runs but "
            "Claude API is not configured. Set ANTHROPIC_API_KEY to enable synthesis."
        )
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Here are today's four agent reports. Synthesize them into a single voice briefing script.

--- FINANCE ---
{finance.get('spoken_summary') or finance.get('raw_output', '')}

--- BUSINESS ---
{business.get('spoken_summary') or business.get('raw_output', '')}

--- MARKETING ---
{marketing.get('spoken_summary') or marketing.get('raw_output', '')}

--- GUIDE ---
{guide.get('spoken_summary') or guide.get('raw_output', '')}

Now write the voice briefing script."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    script = message.content[0].text
    logger.info(f"Briefing synthesized ({len(script)} chars)")
    return script
